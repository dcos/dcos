# escape=`

FROM microsoft/windowsservercore:1709

#SHELL ["powershell", "-Command", "$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue';"]



# Default to PowerShell if no other command specified.
CMD ["powershell.exe", "-NoLogo", "-ExecutionPolicy", "Bypass"]

COPY ./setup-git.ps1 /tmp/
RUN  powershell.exe -file /tmp/setup-git.ps1

COPY ./setup-cmake.ps1 /tmp/
RUN  powershell.exe -file /tmp/setup-cmake.ps1

COPY ./setup-patch.ps1 /tmp/
RUN  powershell.exe -file /tmp/setup-patch.ps1

COPY ./setup-make.ps1 /tmp/
RUN  powershell.exe -file /tmp/setup-make.ps1

COPY ./setup-python27.ps1 /tmp/
RUN  powershell.exe -file /tmp/setup-python27.ps1
#ENV PYTHON_PATH 'C:\Python27;C:\Python27\scripts'

COPY ./setup-erlang.ps1 /tmp/
RUN  powershell.exe -file /tmp/setup-erlang.ps1

COPY ./setup-golang.ps1 /tmp/
RUN  powershell.exe -file /tmp/setup-golang.ps1
ENV GOPATH 'c:\gopath'

ENV GOLANG_PATH 'C:\gopath\bin;c:\go\bin'
ENV GIT_PATH 'C:\Program Files\git\cmd'
ENV CMAKE_PATH 'C:\Program Files\CMake\bin'
ENV GNUWIN32_PATH 'C:\Program Files (x86)\GnuWin32\bin'
ENV ERLANG_PATH 'C:\Program Files\erlang\bin'

RUN setx /m PATH "%PATH%;C:\Bin;%GIT_PATH%;%CMAKE_PATH%;%GNUWIN32_PATH%;%PYTHON_PATH%;%ZIP_PATH%;%ERLANG_PATH%;%GOLANG_PATH%"

# Download useful tools to C:\Bin.
ADD https://dist.nuget.org/win-x86-commandline/v4.1.0/nuget.exe C:\\Bin\\nuget.exe

# Download the Build Tools bootstrapper outside of the PATH.
ADD https://aka.ms/vs/15/release/vs_buildtools.exe C:\\TEMP\\vs_buildtools.exe

# Add C:\Bin to PATH and install Build Tools excluding workloads and components with known issues.
RUN C:\TEMP\vs_buildtools.exe --quiet --wait --norestart --nocache --installPath C:\BuildTools  `
    --add Microsoft.VisualStudio.Workload.MSBuildTools `
    --add Microsoft.VisualStudio.Workload.VCTools `
    --add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
    --add Microsoft.VisualStudio.Component.VC.140 `
    --add Microsoft.VisualStudio.Component.Windows10SDK.16299.Desktop `
    --add Microsoft.VisualStudio.Component.Windows81SDK `
    --add Microsoft.VisualStudio.Component.VC.ATL `
    || IF "%ERRORLEVEL%"=="3010" EXIT 0

# Start developer command prompt with any other commands specified.

ENTRYPOINT C:\BuildTools\Common7\Tools\VsDevCmd.bat &&

