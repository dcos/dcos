-- neturl.lua - a robust url parser and builder
-- https://raw.githubusercontent.com/golgote/neturl/master/lib/net/url.lua
--
-- Bertrand Mansion, 2011-2013; License MIT
-- Copyright (c) 2011-2013 Bertrand Mansion
--
-- Permission is hereby granted, free of charge, to any person obtaining a copy
-- of this software and associated documentation files (the "Software"), to deal
-- in the Software without restriction, including without limitation the rights
-- to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
-- copies of the Software, and to permit persons to whom the Software is
-- furnished to do so, subject to the following conditions:
--
-- The above copyright notice and this permission notice shall be included in
-- all copies or substantial portions of the Software.
--
-- THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
-- IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
-- FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
-- AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
-- LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
-- OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
-- THE SOFTWARE.
-- @module neturl
-- @alias	M

local M = {}
M.version = "0.9.0"

--- url options
-- separator is set to `&` by default but could be anything like `&amp;amp;` or `;`
-- @todo Add an option to limit the size of the argument table
M.options = {
	separator = '&'
}

--- list of known and common scheme ports
-- as documented in <a href="http://www.iana.org/assignments/uri-schemes.html">IANA URI scheme list</a>
M.services = {
	acap     = 674,
	cap      = 1026,
	dict     = 2628,
	ftp      = 21,
	gopher   = 70,
	http     = 80,
	https    = 443,
	iax      = 4569,
	icap     = 1344,
	imap     = 143,
	ipp      = 631,
	ldap     = 389,
	mtqp     = 1038,
	mupdate  = 3905,
	news     = 2009,
	nfs      = 2049,
	nntp     = 119,
	rtsp     = 554,
	sip      = 5060,
	snmp     = 161,
	telnet   = 23,
	tftp     = 69,
	vemmi    = 575,
	afs      = 1483,
	jms      = 5673,
	rsync    = 873,
	prospero = 191,
	videotex = 516
}

local legal = {
	["-"] = true, ["_"] = true, ["."] = true, ["!"] = true,
	["~"] = true, ["*"] = true, ["'"] = true, ["("] = true,
	[")"] = true, [":"] = true, ["@"] = true, ["&"] = true,
	["="] = true, ["+"] = true, ["$"] = true, [","] = true,
	[";"] = true -- can be used for parameters in path
}

local function decode(str)
	local str = str:gsub('+', ' ')
	return (str:gsub("%%(%x%x)", function(c)
			return string.char(tonumber(c, 16))
	end))
end

local function encode(str)
	return (str:gsub("([^A-Za-z0-9%_%.%-%~])", function(v)
			return string.upper(string.format("%%%02x", string.byte(v)))
	end))
end

-- for query values, prefer + instead of %20 for spaces
local function encodeValue(str)
	local str = encode(str)
	return str:gsub('%%20', '+')
end

local function encodeSegment(s)
	local legalEncode = function(c)
		if legal[c] then
			return c
		end
		return encode(c)
	end
	return s:gsub('([^a-zA-Z0-9])', legalEncode)
end

--- builds the url
-- @return a string representing the built url
function M:build()
	local url = ''
	if self.path then
		local path = self.path
		path:gsub("([^/]+)", function (s) return encodeSegment(s) end)
		url = url .. tostring(path)
	end
	if self.query then
		local qstring = tostring(self.query)
		if qstring ~= "" then
			url = url .. '?' .. qstring
		end
	end
	if self.host then
		local authority = self.host
		if self.port and self.scheme and M.services[self.scheme] ~= self.port then
			authority = authority .. ':' .. self.port
		end
		local userinfo
		if self.user and self.user ~= "" then
			userinfo = self.user
			if self.password then
				userinfo = userinfo .. ':' .. self.password
			end
		end
		if userinfo and userinfo ~= "" then
			authority = userinfo .. '@' .. authority
		end
		if authority then
			if url ~= "" then
				url = '//' .. authority .. '/' .. url:gsub('^/+', '')
			else
				url = '//' .. authority
			end
		end
	end
	if self.scheme then
		url = self.scheme .. ':' .. url
	end
	if self.fragment then
		url = url .. '#' .. self.fragment
	end
	return url
end

--- builds the querystring
-- @param tab The key/value parameters
-- @param sep The separator to use (optional)
-- @param key The parent key if the value is multi-dimensional (optional)
-- @return a string representing the built querystring
function M.buildQuery(tab, sep, key)
	local query = {}
	if not sep then
		sep = M.options.separator or '&'
	end
	local keys = {}
	for k in pairs(tab) do
		keys[#keys+1] = k
	end
	table.sort(keys)
	for _,name in ipairs(keys) do
		local value = tab[name]
		name = encode(tostring(name))
		if key then
			name = string.format('%s[%s]', tostring(key), tostring(name))
		end
		if type(value) == 'table' then
			query[#query+1] = M.buildQuery(value, sep, name)
		else
			local value = encodeValue(tostring(value))
			if value ~= "" then
				query[#query+1] = string.format('%s=%s', name, value)
			else
				query[#query+1] = name
			end
		end
	end
	return table.concat(query, sep)
end

--- Parses the querystring to a table
-- This function can parse multidimensional pairs and is mostly compatible
-- with PHP usage of brackets in key names like ?param[key]=value
-- @param str The querystring to parse
-- @param sep The separator between key/value pairs, defaults to `&`
-- @todo limit the max number of parameters with M.options.max_parameters
-- @return a table representing the query key/value pairs
function M.parseQuery(str, sep)
	if not sep then
		sep = M.options.separator or '&'
	end

	local values = {}
	for key,val in str:gmatch(string.format('([^%q=]+)(=*[^%q=]*)', sep, sep)) do
		local key = decode(key)
		local keys = {}
		key = key:gsub('%[([^%]]*)%]', function(v)
				-- extract keys between balanced brackets
				if string.find(v, "^-?%d+$") then
					v = tonumber(v)
				else
					v = decode(v)
				end
				table.insert(keys, v)
				return "="
		end)
		key = key:gsub('=+.*$', "")
		key = key:gsub('%s', "_") -- remove spaces in parameter name
		val = val:gsub('^=+', "")

		if not values[key] then
			values[key] = {}
		end
		if #keys > 0 and type(values[key]) ~= 'table' then
			values[key] = {}
		elseif #keys == 0 and type(values[key]) == 'table' then
			values[key] = decode(val)
		end

		local t = values[key]
		for i,k in ipairs(keys) do
			if type(t) ~= 'table' then
				t = {}
			end
			if k == "" then
				k = #t+1
			end
			if not t[k] then
				t[k] = {}
			end
			if i == #keys then
				t[k] = decode(val)
			end
			t = t[k]
		end
	end
	setmetatable(values, { __tostring = M.buildQuery })
	return values
end

--- set the url query
-- @param query Can be a string to parse or a table of key/value pairs
-- @return a table representing the query key/value pairs
function M:setQuery(query)
	local query = query
	if type(query) == 'table' then
		query = M.buildQuery(query)
	end
	self.query = M.parseQuery(query)
	return query
end

--- set the authority part of the url
-- The authority is parsed to find the user, password, port and host if available.
-- @param authority The string representing the authority
-- @return a string with what remains after the authority was parsed
function M:setAuthority(authority)
	self.authority = authority
	self.port = nil
	self.host = nil
	self.userinfo = nil
	self.user = nil
	self.password = nil

	authority = authority:gsub('^([^@]*)@', function(v)
		self.userinfo = v
		return ''
	end)
	authority = authority:gsub("^%[[^%]]+%]", function(v)
		-- ipv6
		self.host = v
		return ''
	end)
	authority = authority:gsub(':([^:]*)$', function(v)
		self.port = tonumber(v)
		return ''
	end)
	if authority ~= '' and not self.host then
		self.host = authority:lower()
	end
	if self.userinfo then
		local userinfo = self.userinfo
		userinfo = userinfo:gsub(':([^:]*)$', function(v)
				self.password = v
				return ''
		end)
		self.user = userinfo
	end
	return authority
end

--- Parse the url into the designated parts.
-- Depending on the url, the following parts can be available:
-- scheme, userinfo, user, password, authority, host, port, path,
-- query, fragment
-- @param url Url string
-- @return a table with the different parts and a few other functions
function M.parse(url)
	local comp = {}
	M.setAuthority(comp, "")
	M.setQuery(comp, "")

	local url = tostring(url or '')
	url = url:gsub('#(.*)$', function(v)
		comp.fragment = v
		return ''
	end)
	url =url:gsub('^([%w][%w%+%-%.]*)%:', function(v)
		comp.scheme = v:lower()
		return ''
	end)
	url = url:gsub('%?(.*)', function(v)
		M.setQuery(comp, v)
		return ''
	end)
	url = url:gsub('^//([^/]*)', function(v)
		M.setAuthority(comp, v)
		return ''
	end)
	comp.path = decode(url)

	setmetatable(comp, {
		__index = M,
		__tostring = M.build}
	)
	return comp
end

--- removes dots and slashes in urls when possible
-- This function will also remove multiple slashes
-- @param path The string representing the path to clean
-- @return a string of the path without unnecessary dots and segments
function M.removeDotSegments(path)
	local fields = {}
	if string.len(path) == 0 then
		return ""
	end
	local startslash = false
	local endslash = false
	if string.sub(path, 1, 1) == "/" then
		startslash = true
	end
	if (string.len(path) > 1 or startslash == false) and string.sub(path, -1) == "/" then
		endslash = true
	end

	path:gsub('[^/]+', function(c) table.insert(fields, c) end)

	local new = {}
	local j = 0

	for i,c in ipairs(fields) do
		if c == '..' then
			if j > 0 then
				j = j - 1
			end
		elseif c ~= "." then
			j = j + 1
			new[j] = c
		end
	end
	local ret = ""
	if #new > 0 and j > 0 then
		ret = table.concat(new, '/', 1, j)
	else
		ret = ""
	end
	if startslash then
		ret = '/'..ret
	end
	if endslash then
		ret = ret..'/'
	end
	return ret
end

local function absolutePath(base_path, relative_path)
	if string.sub(relative_path, 1, 1) == "/" then
		return '/' .. string.gsub(relative_path, '^[%./]+', '')
	end
	local path = base_path
	if relative_path ~= "" then
		path = '/'..path:gsub("[^/]*$", "")
	end
	path = path .. relative_path
	path = path:gsub("([^/]*%./)", function (s)
		if s ~= "./" then return s else return "" end
	end)
	path = string.gsub(path, "/%.$", "/")
	local reduced
	while reduced ~= path do
		reduced = path
		path = string.gsub(reduced, "([^/]*/%.%./)", function (s)
			if s ~= "../../" then return "" else return s end
		end)
	end
	path = string.gsub(path, "([^/]*/%.%.?)$", function (s)
		if s ~= "../.." then return "" else return s end
	end)
	local reduced
	while reduced ~= path do
		reduced = path
		path = string.gsub(reduced, '^/?%.%./', '')
	end
	return '/' .. path
end

--- builds a new url by using the one given as parameter and resolving paths
-- @param other A string or a table representing a url
-- @return a new url table
function M:resolve(other)
	if type(self) == "string" then
		self = M.parse(self)
	end
	if type(other) == "string" then
		other = M.parse(other)
	end
	if other.scheme then
		return other
	else
		other.scheme = self.scheme
		if not other.authority or other.authority == "" then
			other:setAuthority(self.authority)
			if not other.path or other.path == "" then
				other.path = self.path
				local query = other.query
				if not query or not next(query) then
					other.query = self.query
				end
			else
				other.path = absolutePath(self.path, other.path)
			end
		end
		return other
	end
end

--- normalize a url path following some common normalization rules
-- described on <a href="http://en.wikipedia.org/wiki/URL_normalization">The URL normalization page of Wikipedia</a>
-- @return the normalized path
function M:normalize()
	if type(self) == 'string' then
		self = M.parse(self)
	end
	if self.path then
		local path = self.path
		path = absolutePath(path, "")
		-- normalize multiple slashes
		path = string.gsub(path, "//+", "/")
		self.path = path
	end
	return self
end

return M
