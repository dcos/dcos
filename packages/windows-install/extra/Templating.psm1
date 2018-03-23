# Copyright 2016 Cloudbase Solutions Srl
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#

function Convert-HashtableToDictionary {
    Param(
        [Parameter(Mandatory=$true,ValueFromPipeline=$true)]
        [hashtable]$Data
    )
    $new = [System.Collections.Generic.Dictionary[string, object]](New-Object 'System.Collections.Generic.Dictionary[string, object]')
    foreach($i in $($data.Keys)) {
        $new[$i] = Convert-PSObjectToGenericObject $Data[$i]
    }
    return $new
}

function Convert-ListToGenericList {
    Param(
        [Parameter(Mandatory=$true,ValueFromPipeline=$true)]
        [array]$Data
    )
    $new = [System.Collections.Generic.List[object]](New-Object 'System.Collections.Generic.List[object]')
    foreach($i in $Data) {
        $val = Convert-PSObjectToGenericObject $i
        $new.Add($val)
    }
    return ,$new
}

function Convert-PSCustomObjectToDictionary {
    Param(
        [Parameter(Mandatory=$true,ValueFromPipeline=$true)]
        [PSCustomObject]$Data
    )
    $ret = [System.Collections.Generic.Dictionary[string,object]](New-Object 'System.Collections.Generic.Dictionary[string,object]')
    foreach ($i in $Data.psobject.properties) {
        $ret[$i.Name] = Convert-PSObjectToGenericObject $i.Value
    }
    return $ret
}

function Convert-PSObjectToGenericObject {
    Param(
        [Parameter(Mandatory=$true,ValueFromPipeline=$true)]
        [System.Object]$Data
    )
    # explicitly cast object to its type. Without this, it gets wrapped inside a powershell object
    # which causes YamlDotNet to fail
    $data = $data -as $data.GetType().FullName
    switch($data.GetType()) {
        ($_.FullName -eq "System.Management.Automation.PSCustomObject") {
            return Convert-PSCustomObjectToDictionary $data
        }
        default {
            if (([System.Collections.IDictionary].IsAssignableFrom($_))){
                return Convert-HashtableToDictionary $data
            } elseif (([System.Collections.IList].IsAssignableFrom($_))) {
                return Convert-ListToGenericList $data
            }
            return $data
        }
    }
}

function Invoke-RenderTemplate {
    [CmdletBinding()]
    Param(
        [Parameter(Mandatory=$true, ValueFromPipeline=$true)]
        [hashtable]$Context,
        [Parameter(Mandatory=$true, ValueFromPipeline=$true)]
        [string]$TemplateData
    )
    PROCESS {
        $norm = Convert-PSObjectToGenericObject $Context
        $tpl = [DotLiquid.Template]::Parse($TemplateData)
        $hash = [DotLiquid.Hash]::FromDictionary($norm)
        return  $tpl.Render($hash)
    }
}

function Invoke-RenderTemplateFromFile {
    [CmdletBinding()]
    Param(
        [Parameter(Mandatory=$true, ValueFromPipeline=$true)]
        [hashtable]$Context,
        [Parameter(Mandatory=$true, ValueFromPipeline=$true)]
        [string]$Template
    )
    PROCESS {
        if(!(Test-Path $Template)) {
            Throw "Template $Template was not found"
        }
        $contents = [System.IO.File]::ReadAllText($Template)
        return Invoke-RenderTemplate -Context $Context -TemplateData $contents
    }
}

Export-ModuleMember -Function * -Alias *
