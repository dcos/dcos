local cjson_safe = require "cjson.safe"


local util = {}


function util.get_stripped_first_line_from_file(path)
    -- Return nil when file is emtpy.
    -- Return nil open I/O error.
    -- Log I/O error details.
    local f, err = io.open(path, "rb")
    if f then
        -- *l read mode: read line skipping EOL, return nil on end of file.
        local line = f:read("*l")
        f:close()
        if line then
            return line:strip()
        end
        ngx.log(ngx.ERR, "File is empty: " .. path)
        return nil
    end
    ngx.log(ngx.ERR, "Error reading file `" .. path .. "`: " .. err)
    return nil
end


function util.get_file_content(path)
    local f, err = io.open(path, "rb")
    if f then
        -- *a read mode: read entire file.
        local content = f:read("*a")
        f:close()
        return content
    end
    ngx.log(ngx.ERR, "Error reading file `" .. path .. "`: " .. err)
    return nil
end


-- Monkey-patch string table.

function string:split(sep)
    local sep, fields = sep or " ", {}
    local pattern = string.format("([^%s]+)", sep)
    self:gsub(pattern, function(c) fields[#fields+1] = c end)
    return fields
end


function string.startswith(str, prefix)
    return string.sub(str, 1, string.len(prefix)) == prefix
end


function string:strip()
    -- Strip leading and trailing whitespace.
    -- Ref: http://lua-users.org/wiki/StringTrim
    return self:match "^%s*(.-)%s*$"
end


return util
