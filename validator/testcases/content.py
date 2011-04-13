import hashlib
from StringIO import StringIO

from validator import decorator
from validator import submain as testendpoint_validator
from validator import unicodehelper
import validator.testcases.markup.markuptester as testendpoint_markup
import validator.testcases.markup.csstester as testendpoint_css
import validator.testcases.scripting as testendpoint_js
import validator.testcases.langpack as testendpoint_langpack
from validator.xpi import XPIManager
from validator.constants import *
from validator.textfilter import is_standard_ascii


@decorator.register_test(tier=1)
def test_xpcnativewrappers(err, package_contents=None, xpi_package=None):
    """Tests the chrome.manifest file to ensure that it doesn't contain
    xpcnativewrappers objects."""

    # Don't even both with the test(s) if there's no chrome.manifest.
    chrome = err.get_resource("chrome.manifest")
    if not chrome:
        return None

    for triple in chrome.triples:
        # Test to make sure that the triple's subject is valid
        if triple["subject"] == "xpcnativewrappers":
            err.warning(("testcases_content",
                         "test_xpcnativewrappers",
                         "found_in_chrome_manifest"),
                        "xpcnativewrappers not allowed in chrome.manifest",
                        "chrome.manifest files are not allowed to contain "
                        "xpcnativewrappers directives.",
                        "chrome.manifest",
                        line=triple["line"],
                        context=chrome.context)


@decorator.register_test(tier=2)
def test_packed_packages(err, package_contents=None, xpi_package=None):
    "Tests XPI and JAR files for naughty content."

    processed_files = 0

    hash_whitelist = [x[:-1] for x in
                      open(os.path.join(os.path.dirname(__file__),
                                        'whitelist_hashes.txt')).readlines()]

    # Iterate each item in the package.
    for name, data in package_contents.items():

        if name.startswith("__MACOSX") or \
           name.startswith(".DS_Store"):
            continue

        if name.split("/")[-1].startswith("._"):
            err.notice(("testcases_content",
                        "test_packed_packages",
                        "macintosh_junk"),
                       "Garbage file found.",
                       ["A junk file has been detected. It may cause problems "
                        "with proper operation of the add-on down the road.",
                        "It is recommended that you delete the file"],
                       name)

        try:
            file_data = xpi_package.read(name)
        except KeyError:  # pragma: no cover
            pass

        # Skip over whitelisted hashes
        hash = hashlib.sha1(file_data).hexdigest()
        if hash in hash_whitelist:
            continue

        processed = False
        # If that item is a container file, unzip it and scan it.
        if data["extension"] == "jar":
            # This is either a subpackage or a nested theme.

            # Whether this is a subpackage or a nested theme is
            # determined by whether it is in the root folder or not.
            # Subpackages are always found in a directory such as
            # /chrome or /content.
            is_subpackage = name.count("/") > 0

            # Unpack the package and load it up.
            package = StringIO(file_data)
            sub_xpi = XPIManager(package, name, is_subpackage)
            if not sub_xpi.zf:
                err.error(("testcases_content",
                           "test_packed_packages",
                           "jar_subpackage_corrupt"),
                          "Subpackage corrupt.",
                          "The subpackage could not be opened due to issues "
                          "with corruption. Ensure that the file is valid.",
                          name)
                continue

            temp_contents = sub_xpi.get_file_data()

            # Let the error bunder know we're in a sub-package.
            err.push_state(data["name_lower"])
            err.set_type(PACKAGE_SUBPACKAGE)  # Subpackage
            err.set_tier(1)
            testendpoint_validator.test_inner_package(err,
                                                      temp_contents,
                                                      sub_xpi)
            package.close()
            err.pop_state()
            err.set_tier(2)

        elif data["extension"] == "xpi":
            # It's not a subpackage, it's a nested extension. These are
            # found in multi-extension packages.

            # Unpack!
            package = StringIO(file_data)

            err.push_state(data["name_lower"])
            err.set_tier(1)

            # There are no expected types for packages within a multi-
            # item package.
            testendpoint_validator.test_package(err, package, name)

            package.close()
            err.pop_state()
            err.set_tier(2)  # Reset to the current tier

        elif data["extension"] in ("xul", "xml", "html", "xhtml"):

            parser = testendpoint_markup.MarkupParser(err)
            parser.process(name,
                           file_data,
                           data["extension"])

            processed = True

        elif data["extension"] in ("css", "js", "jsm"):

            if not file_data:
                continue

            # Convert the file data to unicode
            file_data = unicodehelper.decode(file_data)

            if data["extension"] == "css":
                testendpoint_css.test_css_file(err,
                                               name,
                                               file_data)
            elif data["extension"] in ("js", "jsm"):
                testendpoint_js.test_js_file(err,
                                             name,
                                             file_data)
        # This is tested in test_langpack.py
        if err.detected_type == PACKAGE_LANGPACK and not processed:

            testendpoint_langpack.test_unsafe_html(err,
                                                   name,
                                                   file_data)

        # This aids in creating unit tests.
        processed_files += 1

    return processed_files

