# escape=`
# The above line changes the default escape character to back-tick as
# windows uses the default backslash for filenames making filepaths hard
# to read

FROM microsoft/windowsservercore:1709

# Default to PowerShell if no other command specified.
CMD ["powershell.exe", "-NoLogo", "-ExecutionPolicy", "Bypass"]

COPY .\setup-pwsh.ps1 c:\temp\
RUN powershell.exe -File c:\temp\setup-pwsh.ps1

COPY .\setup-git.ps1 c:\temp\
RUN pwsh.exe c:\temp\setup-git.ps1

COPY .\setup-python36.ps1 c:\temp\
RUN pwsh.exe c:\temp\setup-python36.ps1

COPY .\setup-cmake.ps1 c:\temp\
RUN pwsh.exe c:\temp\setup-cmake.ps1

COPY .\setup-patch.ps1 c:\temp\
RUN pwsh.exe c:\temp\setup-patch.ps1

COPY .\setup-make.ps1 c:\temp\
RUN pwsh.exe c:\temp\setup-make.ps1

COPY .\setup-erlang.ps1 c:\temp\
RUN pwsh.exe c:\temp\setup-erlang.ps1

COPY .\setup-golang.ps1 c:\temp\
RUN pwsh.exe c:\temp\setup-golang.ps1

ENV GOPATH 'c:\gopath'
ENV PYTHON_PATH 'C:\Python36'
ENV GOLANG_PATH 'C:\gopath\bin;c:\go\bin'
ENV GIT_PATH 'C:\Program Files\git\cmd'
ENV CMAKE_PATH 'C:\Program Files\CMake\bin'
ENV GNUWIN32_PATH 'C:\Program Files (x86)\GnuWin32\bin'
ENV ERLANG_PATH 'C:\Program Files\erlang\bin'

RUN setx /m PATH "%PATH%;C:\Bin;%GIT_PATH%;%CMAKE_PATH%;%PYTHON_PATH%;%GNUWIN32_PATH%;%ZIP_PATH%;%ERLANG_PATH%;%GOLANG_PATH%"

COPY .\setup-nuget.ps1 c:\temp\
RUN pwsh.exe c:\temp\setup-nuget.ps1

COPY .\setup-vs_buildtools.ps1 c:\temp\
RUN pwsh.exe c:\temp\setup-vs_buildtools.ps1

# Start developer command prompt with any other commands specified.
ENTRYPOINT C:\BuildTools\Common7\Tools\VsDevCmd.bat && pwsh.exe
