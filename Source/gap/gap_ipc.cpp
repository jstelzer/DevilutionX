#include "gap_ipc.h"
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <fcntl.h>
#include <cstring>
#include <iostream>
#include <vector>

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
    
    bool Initialize() {
        unlink(SOCKET_PATH);
        
        server_fd_ = socket(AF_UNIX, SOCK_STREAM, 0);
        if (server_fd_ == -1) {
            std::cerr << "GAP IPC: Failed to create socket" << std::endl;
            return false;
        }
        
        sockaddr_un addr;
        memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, SOCKET_PATH, sizeof(addr.sun_path) - 1);
        
        if (bind(server_fd_, (struct sockaddr*)&addr, sizeof(addr)) == -1) {
            std::cerr << "GAP IPC: Failed to bind socket" << std::endl;
            Cleanup();
            return false;
        }
        
        if (listen(server_fd_, 1) == -1) {
            std::cerr << "GAP IPC: Failed to listen on socket" << std::endl;
            Cleanup();
            return false;
        }
        
        int flags = fcntl(server_fd_, F_GETFL, 0);
        fcntl(server_fd_, F_SETFL, flags | O_NONBLOCK);
        
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
            int flags = fcntl(client_fd_, F_GETFL, 0);
            fcntl(client_fd_, F_SETFL, flags | O_NONBLOCK);
            std::cout << "GAP IPC: Agent connected" << std::endl;
            return true;
        }
        return false;
    }
    
    bool SendMessage(const std::string& message) {
        AcceptConnection();
        if (client_fd_ == -1) return false;
        
        uint32_t length = message.size();
        if (write(client_fd_, &length, sizeof(length)) != sizeof(length)) {
            return false;
        }
        if (write(client_fd_, message.c_str(), length) != static_cast<ssize_t>(length)) {
            return false;
        }
        return true;
    }
    
    bool ReceiveMessage(std::string& message) {
        AcceptConnection();
        if (client_fd_ == -1) return false;
        
        uint32_t length;
        ssize_t n = read(client_fd_, &length, sizeof(length));
        if (n != sizeof(length)) {
            if (n == 0) {
                std::cout << "GAP IPC: Agent disconnected" << std::endl;
                close(client_fd_);
                client_fd_ = -1;
            }
            return false;
        }
        
        if (length > 1024 * 1024) {
            std::cerr << "GAP IPC: Message too large: " << length << std::endl;
            return false;
        }
        
        recv_buffer_.resize(length);
        n = read(client_fd_, recv_buffer_.data(), length);
        if (n != static_cast<ssize_t>(length)) {
            return false;
        }
        
        message.assign(recv_buffer_.begin(), recv_buffer_.begin() + length);
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