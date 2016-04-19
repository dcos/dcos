import subprocess


def run(cmd, *args, **kwargs):
    proc = subprocess.Popen(cmd, *args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    stdout, stderr = proc.communicate()
    print("STDOUT: ", stdout.decode('utf-8'))
    print("STDERR: ", stderr.decode('utf-8'))

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)

    assert len(stderr) == 0
    return stdout.decode('utf-8')
