#pragma once

#include <string>
#include <sstream>
#include <vector>
#include <cstdint>

namespace devilution::gap {

class JsonBuilder {
public:
    JsonBuilder& BeginObject();
    JsonBuilder& EndObject();
    JsonBuilder& BeginArray();
    JsonBuilder& EndArray();
    
    JsonBuilder& AddString(const std::string& key, const std::string& value);
    JsonBuilder& AddInt(const std::string& key, int value);
    JsonBuilder& AddUInt(const std::string& key, uint32_t value);
    JsonBuilder& AddBool(const std::string& key, bool value);
    JsonBuilder& AddArray(const std::string& key, const std::vector<int>& values);
    
    JsonBuilder& AddRaw(const std::string& key, const std::string& json);
    
    std::string ToString() const { return ss_.str(); }
    
private:
    std::stringstream ss_;
    bool needs_comma_ = false;
    
    void AddComma();
    void AddKey(const std::string& key);
};

class JsonParser {
public:
    JsonParser(const std::string& json) : json_(json), pos_(0) {}
    
    bool ParseObject();
    std::string GetString(const std::string& key) const;
    int GetInt(const std::string& key) const;
    bool HasKey(const std::string& key) const;
    
    std::string GetObjectString(const std::string& key) const;
    
private:
    std::string json_;
    size_t pos_;
    
    void SkipWhitespace();
    bool ParseString(std::string& out);
    bool ParseValue(std::string& out);
    bool FindKey(const std::string& key, size_t& value_start, size_t& value_end) const;
};

} // namespace devilution::gap