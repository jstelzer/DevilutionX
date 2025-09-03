#include "gap_json.h"
#include <algorithm>

namespace devilution::gap {

JsonBuilder& JsonBuilder::BeginObject() {
    ss_ << "{";
    needs_comma_ = false;
    return *this;
}

JsonBuilder& JsonBuilder::EndObject() {
    ss_ << "}";
    needs_comma_ = true;
    return *this;
}

JsonBuilder& JsonBuilder::BeginArray() {
    ss_ << "[";
    needs_comma_ = false;
    return *this;
}

JsonBuilder& JsonBuilder::EndArray() {
    ss_ << "]";
    needs_comma_ = true;
    return *this;
}

void JsonBuilder::AddComma() {
    if (needs_comma_) {
        ss_ << ",";
    }
    needs_comma_ = true;
}

void JsonBuilder::AddKey(const std::string& key) {
    AddComma();
    ss_ << "\"" << key << "\":";
}

JsonBuilder& JsonBuilder::AddString(const std::string& key, const std::string& value) {
    AddKey(key);
    ss_ << "\"" << value << "\"";
    return *this;
}

JsonBuilder& JsonBuilder::AddInt(const std::string& key, int value) {
    AddKey(key);
    ss_ << value;
    return *this;
}

JsonBuilder& JsonBuilder::AddUInt(const std::string& key, uint32_t value) {
    AddKey(key);
    ss_ << value;
    return *this;
}

JsonBuilder& JsonBuilder::AddBool(const std::string& key, bool value) {
    AddKey(key);
    ss_ << (value ? "true" : "false");
    return *this;
}

JsonBuilder& JsonBuilder::AddArray(const std::string& key, const std::vector<int>& values) {
    AddKey(key);
    ss_ << "[";
    for (size_t i = 0; i < values.size(); i++) {
        if (i > 0) ss_ << ",";
        ss_ << values[i];
    }
    ss_ << "]";
    return *this;
}

JsonBuilder& JsonBuilder::AddRaw(const std::string& key, const std::string& json) {
    AddKey(key);
    ss_ << json;
    return *this;
}

void JsonParser::SkipWhitespace() {
    while (pos_ < json_.size() && std::isspace(json_[pos_])) {
        pos_++;
    }
}

bool JsonParser::ParseObject() {
    SkipWhitespace();
    if (pos_ >= json_.size() || json_[pos_] != '{') {
        return false;
    }
    return true;
}

bool JsonParser::ParseString(std::string& out) {
    SkipWhitespace();
    if (pos_ >= json_.size() || json_[pos_] != '"') {
        return false;
    }
    pos_++;
    
    size_t start = pos_;
    while (pos_ < json_.size() && json_[pos_] != '"') {
        if (json_[pos_] == '\\') pos_++;
        pos_++;
    }
    
    if (pos_ >= json_.size()) {
        return false;
    }
    
    out = json_.substr(start, pos_ - start);
    pos_++;
    return true;
}

bool JsonParser::FindKey(const std::string& key, size_t& value_start, size_t& value_end) const {
    std::string search = "\"" + key + "\":";
    size_t key_pos = json_.find(search);
    
    if (key_pos == std::string::npos) {
        return false;
    }
    
    value_start = key_pos + search.length();
    
    while (value_start < json_.size() && std::isspace(json_[value_start])) {
        value_start++;
    }
    
    if (value_start >= json_.size()) {
        return false;
    }
    
    value_end = value_start;
    
    if (json_[value_start] == '"') {
        value_end++;
        while (value_end < json_.size() && json_[value_end] != '"') {
            if (json_[value_end] == '\\') value_end++;
            value_end++;
        }
        if (value_end < json_.size()) value_end++;
    } else if (json_[value_start] == '{' || json_[value_start] == '[') {
        char open = json_[value_start];
        char close = (open == '{') ? '}' : ']';
        int depth = 1;
        value_end++;
        
        while (value_end < json_.size() && depth > 0) {
            if (json_[value_end] == open) depth++;
            else if (json_[value_end] == close) depth--;
            value_end++;
        }
    } else {
        while (value_end < json_.size() && 
               json_[value_end] != ',' && 
               json_[value_end] != '}' && 
               json_[value_end] != ']') {
            value_end++;
        }
    }
    
    return true;
}

std::string JsonParser::GetString(const std::string& key) const {
    size_t start, end;
    if (!FindKey(key, start, end)) {
        return "";
    }
    
    if (json_[start] == '"') {
        return json_.substr(start + 1, end - start - 2);
    }
    
    return json_.substr(start, end - start);
}

int JsonParser::GetInt(const std::string& key) const {
    std::string value = GetString(key);
    if (value.empty()) return 0;
    return std::stoi(value);
}

bool JsonParser::HasKey(const std::string& key) const {
    size_t start, end;
    return FindKey(key, start, end);
}

std::string JsonParser::GetObjectString(const std::string& key) const {
    size_t start, end;
    if (!FindKey(key, start, end)) {
        return "{}";
    }
    return json_.substr(start, end - start);
}

} // namespace devilution::gap