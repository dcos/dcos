# escape=`
# The above line changes the default escape character to back-tick as
# windows uses the default backslash for filenames making filepaths hard
# to read

FROM microsoft/windowsservercore:1709

# Default to PowerShell if no other command specified.
CMD ["powershell.exe", "-NoLogo", "-ExecutionPolicy", "Bypass"]

ADD https://github.com/git-for-windows/git/releases/download/v2.16.1.windows.1/Git-2.16.1-64-bit.exe c:\temp\Git-2.16.1-64-bit.exe
COPY .\setup-git.ps1 \temp\
RUN  powershell.exe -file c:\temp\setup-git.ps1

ADD https://cmake.org/files/v3.9/cmake-3.9.0-win64-x64.msi c:\temp\cmake-3.9.0-win64-x64.msi
COPY .\setup-cmake.ps1 \temp\
RUN  powershell.exe -file c:\temp\setup-cmake.ps1

ADD https://10gbps-io.dl.sourceforge.net/project/gnuwin32/patch/2.5.9-7/patch-2.5.9-7-setup.exe c:\temp\patch-2.5.9-7-setup.exe
COPY .\setup-patch.ps1 \temp\
RUN  powershell.exe -file c:\temp\setup-patch.ps1

ADD http://internode.dl.sourceforge.net/project/gnuwin32/make/3.81/make-3.81.exe c:\temp\make-3.81.exe
COPY .\setup-make.ps1 \temp\
RUN  powershell.exe -file c:\temp\setup-make.ps1

ADD http://erlang.org/download/otp_win64_19.3.exe c:\temp\otp_win64_19.3.exe
COPY .\setup-erlang.ps1 \temp\
RUN  powershell.exe -file c:\temp\setup-erlang.ps1

ADD https://golang.org/dl/go1.9.3.windows-amd64.zip c:\temp\go1.9.3.windows-amd64.zip
COPY .\setup-golang.ps1 \temp\
RUN  powershell.exe -file c:\temp\setup-golang.ps1
ENV GOPATH 'c:\gopath'

ENV GOLANG_PATH 'C:\gopath\bin;c:\go\bin'
ENV GIT_PATH 'C:\Program Files\git\cmd'
ENV CMAKE_PATH 'C:\Program Files\CMake\bin'
ENV GNUWIN32_PATH 'C:\Program Files (x86)\GnuWin32\bin'
ENV ERLANG_PATH 'C:\Program Files\erlang\bin'

RUN setx /m PATH "%PATH%;C:\Bin;%GIT_PATH%;%CMAKE_PATH%;%GNUWIN32_PATH%;%ZIP_PATH%;%ERLANG_PATH%;%GOLANG_PATH%"

# Download useful tools to C:\Bin.
ADD https://dist.nuget.org/win-x86-commandline/v4.1.0/nuget.exe C:\Bin\nuget.exe

# Download the Build Tools bootstrapper outside of the PATH.
ADD https://aka.ms/vs/15/release/vs_buildtools.exe C:\TEMP\vs_buildtools.exe

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

ENTRYPOINT C:\BuildTools\Common7\Tools\VsDevCmd.bat && powershell.exe -file