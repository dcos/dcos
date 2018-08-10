$ErrorActionPreference = "stop"

Function Touch-File($file)
{
    if($file -eq $null) {
        throw "No filename supplied"
    }

    if(Test-Path $file)
    {
        (Get-ChildItem $file).LastWriteTime = Get-Date
    }
    else
    {
        $null | out-file -encoding ascii $file
    }
}

# Make files in bin/lib will likely touch bin, lib of output. Test that.
new-item -itemtype Directory "$env:PKG_PATH\bin","$env:PKG_PATH\lib","$env:PKG_PATH\dcos.target.wants"

Touch-File "$env:PKG_PATH\bin\mesos-master"
Touch-File "$env:PKG_PATH\lib\libmesos.so"
Touch-File "$env:PKG_PATH\dcos.target.wants\dcos-foo.service"
Write-Output "$env:PKG_VERSION" > "$env:PKG_PATH\version"
Touch-File "$env:PKG_PATH\$env:PKG_NAME"
