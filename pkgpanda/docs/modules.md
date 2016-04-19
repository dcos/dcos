# Module Design

There are several mesos  modules so that we can add slave endpoints which cause
all of the packaging, provisioning, etc. actions to take place.

All of these modules simply add new libprocess processes to mesos. These
processes will take HTTP requests, and turn them into running a subprocess which
will perform the actual actions. The command line will be the effective ABI
between the module and the code performing the actions which is written in
python currently (although could be any language).

## Module implementation layout

In progress, point person is Till building a PoC module.

The modules will be Lifecycle Modules inside of Mesos. Inside each module we try
to keep the C++ as simple and repeatable/predictable as possible.

The module will define a new libprocess Process and its routes. It will then
execute subprocesses to carry out the actions of the different routes.

If the module needs to communicate out, it should write information to stdout to
be returned to the caller.

If it needs to make API calls to remote services, it should do them itself using
an HTTP library.

## Example

Note: This code is incorrect, doesn't compile, etc. It is just a sample of how
the modules are structured. Till should hopefully have a complete sample module
soon.

class PackagerProcess : public Process<PackagerProcess>
{
  PackagerProcess() : ProcessBase("pkgpanda") {}
  void initialize() final {
    route("/list.json", None, &PackagerProcess::List);
    route("/add", None, &PackagerProcess::Add);
    route("/remove", None, &PackagerProcess::Remove);
  }

  Future<Response> PackagerProcess::list(const Request& request)
  {
    // No arguments are needed, just call straight through
    Try<Subproess> subprocess("pkgpanda", {"list","--format=json"});
    if (subprocess.isError()) {
      return InternalServerError(subprocess.error());
    }

    // TODO(cmaloney): We don't block here, rather write a process helper which
    // returns a Response which is fed it's body through stdout/a special well-defined
    // format.
    // TODO(cmaloney): We need to pipe data from the subprocess to this process while
    // it is written to stdout/stderr otherwise the subprocess may block / be paused
    // because stdout/stderr is full.
    // Python documents this well at: https://docs.python.org/3/library/subprocess.html
    int status = subprocess.get().status().get();

    // Read out stdout and send it back as a response body
    return OK(os::read(subprocess.get().out().get(), infinite));
  }

}


class Module
