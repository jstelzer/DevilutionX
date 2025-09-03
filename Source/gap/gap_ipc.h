#pragma once

#include <string>
#include <memory>

namespace devilution::gap {

class GapIPC {
public:
    GapIPC();
    ~GapIPC();
    
    bool Initialize();
    void Shutdown();
    
    bool SendMessage(const std::string& message);
    bool ReceiveMessage(std::string& message);
    
private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace devilution::gap