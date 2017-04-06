# DC/OS Python Style Guide
###### Version 0.1
###### April-6-2017

For Python source code within DC/OS project, we prefer to keep [Google Python Style Guide Revision 2.59] as the base and
**extend** it with some changes that will make DC/OS codebase look modern, consistent and easy to follow.

##### Rationale

With any style guide, the primary requirement is to adopt one and follow it consistently. With our choices below, we
can use tools available in the python ecosystem to our advantage, enforce consistency in our codebase, while creating
and publishing automatically generated documentation from the code itself.

##### Versioned document

Styleguide _conventions_ are not set in stone. We can improve upon this or remove inconvenient styles by creating a PR,
discussing the merits or demerits to arrive at a consensus. Developers who contribute code to the DC/OS repo are the
main stake holders of this style guide.

##### Python Version Requirement

This style guide is written for Python3.5 and above. As new features of the language get standardized, this style guide
can be revised to adopt new features.

#### Base Style Guide

* [Google Python Style Guide Revision 2.59]


#### DC/OS Specific extensions to Base Style Guide

* Import Requirements
    * Adopt the base style guide preferences.

        ```
        Use import x for importing packages and modules.
        Use from x import y where x is the package prefix and y is the module name with no prefix.
        Use from x import y as z if two modules named y are to be imported or if y is an inconveniently long name.
        ```
    * Use `__init__.py` only to represent python packages.
        * Prefer empty `__init__.py` modules. Keep definitions in submodules.

    _Rationale_: Keeping `__init__.py` empty helps in avoid unnecessary imports when you import a submodule from
    package. Plus,it helps in navigating the code base you know that an object is strictly defined in a submodule and
    not aliased in `__init__.py`

* Import formatting

    * The types of imports should be separated by single line and order should be.

        1. standard library imports.
        2. third-party imports.
        3. application specific imports.

    * Each group of these imports should be sorted.

    _Rationale_:  Readablity is the reason for this separation.

For Example

```
import json
import logging
from subprocess import CalledProcessError
from typing import Callable, List

import retrying
from retrying import RetryError, retry

import test_util.aws
import test_util.cluster
from pkgpanda.util import logger, write_string
from teamcity.messages import TeamcityServiceMessages
from test_util.cluster import run_bootstrap_nginx
from test_util.helpers import (CI_CREDENTIALS,
                               marathon_app_id_to_mesos_dns_subdomain,
                               random_id)
```


* [Packages](https://google.github.io/styleguide/pyguide.html?showone=Packages#Packages)
    * Import each module using the full pathname location of the module.
    * No Relative Imports.

  _Rationale_ - Relative imports are hard to follow and hard to write in consistent manner. And if you are using IDEs
  to navigate the code base, it is much easier to get your code navigation right with absolute imports from the source
  root.

* Maximum line length is 120 characters.
    * Following are the exceptions to this rule. These types can be of arbitrary length.
        * URLs in comments.
        * Any sequence of chars, like embedded tokens which would better be in a single line.

   _Rationale_: At the time this style guide was written, the existing code base followed 120 column width guideline.
   We are keeping up with that.

* Indentation

    * Use 4-space indentation.
    * For long list of arguments, always use double-indented
      hanging-indentation. See example below.
    * The hanging indentation should be followed by a single blank line.

    _Rationale_: This improves the readability of the code. White space is significant in Python, the double
    indentation is to signify that this code block is indented for visual purpose and is continuation segment. This is
    separate from the 4-space indented context-block of program flow.


    * exceeds 120 chars # BAD.

    ```
    def method():

        installer.setup_remote(tunnel=bootstrap_host_tunnel, installer_path=cluster.ssher.home_dir + '/dcos_generate_config.sh', download_url=installer_url)
    ```

    * single indented - Not recommended. # BAD.
    * Note hanging indentation aligns with the logical indentation of the program.

    ```
    def method():
        if installer.prereqs.ok:
            print("pre-reqs satisfied")

        installer.setup_remote(
            tunnel=bootstrap_host_tunnel,
            installer_path=cluster.ssher.home_dir + '/dcos_generate_config.sh',
            download_url=installer_url)

        if installer.setup.ok:
            print("remote setup successful.")
        else:
            print("remote setup successful.")
    ```

   * double indented - Recommended # GOOD. Note the visual clarity.

    ```
    def method():
        if installer.prereqs.ok:
            print("pre-reqs satisfied")

        installer.setup_remote(
                tunnel=bootstrap_host_tunnel,
                installer_path=cluster.ssher.home_dir + '/dcos_generate_config.sh',
                download_url=installer_url)

        if installer.setup.ok:
            print("remote setup successful.")
        else:
            print("remote setup successful.")
    ```


* Adding Types. Since our code-base is Python3.5+ compatible, we have the choice of introducing types, validating
  with mypy.

```
        class VpcClusterUpgradeTestDcosApiSessionFactory:

            def apply(
                    self,
                    dcos_url: str,
                    masters: List[str],
                    public_masters: List[str],
                    slaves: List[str],
                    public_slaves: List[str],
                    default_os_user: str) -> DcosApiSession:
```

* Reviewers will request the author to write types for the method parameters.

    _Rationale_: We will start running mypy type checker as part of build process.


* Shebang Rule.
    * We will consistently use the shebang line in our scripts.
        * `#!/usr/bin/env python3`
        OR
        * `#!/usr/bin/env python2` in our scripts.

    _Rationale_ : Across platforms, and different python versions in a given platform, this is the most consistent way
    to indicate the interpreter required for your python program.

* Use the `format` method
    * Prefer `'{named}'.format` will be over `{}.format`.
        * Rationale: If the number of arguments are long. `{named}.format` helps in readability.
    * Use your best judgement to decide between + and % (or format) when applicable.
    * This style guide does not recommend [f-strings](https://www.python.org/dev/peps/pep-0498/) as `f-strings` are
      still very early feature in Python, yet to be seen wide adoption, and it is available only from
      Python 3.6 onwards.

     _Rationale_: When there are multiple format specifiers used in a string, `{name1} {name2}` formats are easier
    to read than `{}{}` (empty) or `{0}{1}` (indexed) formats.



* TODO Comment Format
    * Follow the rules on [when to write TODO comments](https://google.github.io/styleguide/pyguide.html?showone=TODO_Comments#TODO_Comments)
    * Format required will be `# TODO(active-developer): DCOS_OSS-1234 - Brief one line description.`

    ```
    # TODO(skumaran): DCOS_OSS-952 - Create a flake8 plugin to enforce TODO format.
    ```

    _Rationale_: With every todo, there is active developer associated and JIRA ticket possibly has more discussion
    for the TODO.

* [Comments and Docstrings](https://google.github.io/styleguide/pyguide.html?showone=Comments#Comments).
    * All public classes, methods, functions should be documented.
    * Private classes, which should be indicated by `_leading_underscore` in the name need not be documented.
    * Follow the base style guidelines to adopt the style that explains arguments, return value and exceptions.

```
class DcosApiSession(ARNodeApiClientMixin, ApiClientSession):
    def __init__(
            self,
            dcos_url: str,
            masters: List[str],
            public_masters: List[str],
            slaves: List[str],
            public_slaves: List[str],
            default_os_user: str,
            auth_user: Optional[DcosUser]) -> None:

        """Proxy class for DC/OS clusters.

        This class provides facilities to interact with the DC/OS Cluster launched in the integration tests.


        Args:
            dcos_url: address for the DC/OS web UI.
            masters: list of Mesos master advertised IP addresses.
            public_masters: list of Mesos master IP addresses routable from
                the local host.
            slaves: list of Mesos slave/agent advertised IP addresses.
            default_os_user: default user that marathon/metronome will launch tasks under
            auth_user: use this user's auth for all requests
                Note: user must be authenticated explicitly or call self.wait_for_dcos()

        Returns:
            None

        Raises:
            AssertionError: On empty values.
            Exception: When a given node is not recognized within the DC/OS Cluster.
        """
```

   _Rationale_: We can use sphinx documentation generator. Tools like [sphinx-napolean plugin](https://sphinxcontrib-napoleon.readthedocs.io/en/latest/) can be used to automatically generate api documentation with the above chosen convention.

#### Style Enforcements.

* tox will be configured to run pycodestyle/ pylint to enforce the style requirements.
* With python code type-hint specified, we will use `mypy` in the test suite to check for type incompatibility problems
  before build process.
* We will utilize tools like isort, yapf that assist in adherence to coding style guidelines.

[Google Python Style Guide Revision 2.59]: https://google.github.io/styleguide/pyguide.html
