#include "gap_ipc.h"
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <fcntl.h>
#include <cerrno>
#include <cstring>
#include <iostream>
#include <vector>
#include <sys/stat.h>
#include <sys/ioctl.h>   // FIONREAD
#include <poll.h>        // (optional) could use poll if you prefer
#include <csignal>       // For signal handling

namespace devilution::gap {

static const char* SOCKET_PATH = "/tmp/devilutionx-gap.sock";

class GapIPC::Impl {
public:
    int server_fd_ = -1;
    int client_fd_ = -1;
    std::vector<uint8_t> recv_buffer_;

    ~Impl() {
        Cleanup();
    }

    static bool set_nonblock(int fd, bool on) {
        int flags = fcntl(fd, F_GETFL, 0);
        if (flags == -1) return false;
        if (on) flags |= O_NONBLOCK;
        else flags &= ~O_NONBLOCK;
        return fcntl(fd, F_SETFL, flags) != -1;
    }

    static bool read_full(int fd, void* buf, size_t len) {
        uint8_t* p = static_cast<uint8_t*>(buf);
        size_t nread = 0;
        while (nread < len) {
            ssize_t r = ::read(fd, p + nread, len - nread);
            if (r > 0) { nread += static_cast<size_t>(r); continue; }
            if (r == 0) return false; // peer closed
            if (errno == EINTR) continue;
            if (errno == EAGAIN || errno == EWOULDBLOCK) { usleep(1000); continue; }
            return false;
        }
        return true;
    }

    static bool write_full(int fd, const void* buf, size_t len) {
        const uint8_t* p = static_cast<const uint8_t*>(buf);
        size_t nwritten = 0;
        while (nwritten < len) {
            ssize_t w = ::write(fd, p + nwritten, len - nwritten);
            if (w > 0) { nwritten += static_cast<size_t>(w); continue; }
            if (w == 0) continue;
            if (errno == EINTR) continue;
            if (errno == EAGAIN || errno == EWOULDBLOCK) { usleep(1000); continue; }
            // EPIPE means broken pipe (client disconnected) - don't crash
            if (errno == EPIPE) return false;
            return false;
        }
        return true;
    }

    static socklen_t sockaddr_len(const sockaddr_un& addr) {
#ifdef __APPLE__
        return static_cast<socklen_t>(
            offsetof(struct sockaddr_un, sun_path) + strlen(addr.sun_path));
#else
        (void)addr;
        return sizeof(sockaddr_un);
#endif
    }

    bool Initialize() {
        // Ignore SIGPIPE to prevent crashes when writing to closed sockets
        signal(SIGPIPE, SIG_IGN);

        unlink(SOCKET_PATH);

        server_fd_ = socket(AF_UNIX, SOCK_STREAM, 0);
        if (server_fd_ == -1) {
            std::cerr << "GAP IPC: Failed to create socket: " << strerror(errno) << std::endl;
            return false;
        }

        sockaddr_un addr;
        memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, SOCKET_PATH, sizeof(addr.sun_path) - 1);

        socklen_t len = sockaddr_len(addr);
        if (bind(server_fd_, (struct sockaddr*)&addr, len) == -1) {
            std::cerr << "GAP IPC: Failed to bind socket: " << strerror(errno) << std::endl;
            Cleanup();
            return false;
        }

        // Lock down perms for local agent only
        chmod(SOCKET_PATH, 0600);

        if (listen(server_fd_, 1) == -1) {
            std::cerr << "GAP IPC: Failed to listen on socket: " << strerror(errno) << std::endl;
            Cleanup();
            return false;
        }

        set_nonblock(server_fd_, true); // non-blocking accept()
        recv_buffer_.reserve(65536);

        std::cout << "GAP IPC: Listening on " << SOCKET_PATH << std::endl;
        return true;
    }

    void Cleanup() {
        if (client_fd_ != -1) {
            close(client_fd_);
            client_fd_ = -1;
        }
        if (server_fd_ != -1) {
            close(server_fd_);
            server_fd_ = -1;
        }
        unlink(SOCKET_PATH);
    }

    bool AcceptConnection() {
        if (client_fd_ != -1) return true;

        client_fd_ = accept(server_fd_, nullptr, nullptr);
        if (client_fd_ != -1) {
            // Keep client NON-BLOCKING; ReceiveMessage will be edge-safe.
            set_nonblock(client_fd_, true);
#ifdef __APPLE__
            int one = 1;
            setsockopt(client_fd_, SOL_SOCKET, SO_NOSIGPIPE, &one, sizeof(one));
#endif
            std::cout << "GAP IPC: Agent connected" << std::endl;
            return true;
        }
        return false;
    }

    bool SendMessage(const std::string& message) {
        AcceptConnection();
        if (client_fd_ == -1) return false;

        uint32_t length = message.size();
        bool success = write_full(client_fd_, &length, sizeof(length)) &&
                       write_full(client_fd_, message.data(), length);

        if (!success) {
            // Write failed - likely client disconnected
            std::cout << "GAP IPC: Agent disconnected (write error)" << std::endl;
            close(client_fd_);
            client_fd_ = -1;
            return false;
        }

        return true;
    }

    bool ReceiveMessage(std::string& message) {
        AcceptConnection();
        if (client_fd_ == -1) return false;

        // Non-blocking path: check how many bytes are queued
        int available = 0;
        if (ioctl(client_fd_, FIONREAD, &available) == -1) {
            // If ioctl fails for some reason, be safe and don't block
            if (errno == EWOULDBLOCK || errno == EAGAIN) return false;
            // Other hard errors: treat as disconnect
            std::cout << "GAP IPC: Agent disconnected (ioctl error)" << std::endl;
            close(client_fd_);
            client_fd_ = -1;
            return false;
        }

        if (available < static_cast<int>(sizeof(uint32_t))) {
            // Not enough for the length header yet; try next tick
            return false;
        }

        // Peek header to learn payload size without consuming it
        uint32_t length = 0;
        ssize_t peeked = recv(client_fd_, &length, sizeof(length), MSG_PEEK);
        if (peeked < static_cast<ssize_t>(sizeof(uint32_t))) {
            // Nothing reliable to read yet
            return false;
        }

        if (length > 1024 * 1024) {
            std::cerr << "GAP IPC: Message too large: " << length << std::endl;
            // Consume and drop? For now, treat as error.
            return false;
        }

        // If full message isn't available yet, bail early (avoid blocking)
        if (available < static_cast<int>(sizeof(uint32_t) + length)) {
            return false;
        }

        // Now actually consume header and body (won't block; we checked availability)
        // Consume the header
        uint32_t hdr = 0;
        if (!read_full(client_fd_, &hdr, sizeof(hdr))) {
            std::cout << "GAP IPC: Agent disconnected (header)" << std::endl;
            close(client_fd_);
            client_fd_ = -1;
            return false;
        }

        recv_buffer_.resize(hdr);
        if (!read_full(client_fd_, recv_buffer_.data(), hdr)) {
            std::cout << "GAP IPC: Agent disconnected (body)" << std::endl;
            close(client_fd_);
            client_fd_ = -1;
            return false;
        }

        message.assign(recv_buffer_.begin(), recv_buffer_.end());
        return true;
    }
};

GapIPC::GapIPC() : impl_(std::make_unique<Impl>()) {}
GapIPC::~GapIPC() = default;

bool GapIPC::Initialize() {
    return impl_->Initialize();
}

void GapIPC::Shutdown() {
    impl_->Cleanup();
}

bool GapIPC::SendMessage(const std::string& message) {
    return impl_->SendMessage(message);
}

bool GapIPC::ReceiveMessage(std::string& message) {
    return impl_->ReceiveMessage(message);
}

} // namespace devilution::gap
