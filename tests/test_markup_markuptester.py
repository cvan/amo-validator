﻿# -*- coding: utf-8 -*-
from nose.tools import eq_

import validator.testcases.markup.markuptester as markuptester
from validator.errorbundler import ErrorBundle
from validator.constants import *


def _do_test(path, should_fail=False, type_=None):
    return _do_test_raw(open(path).read(),
                        path,
                        should_fail,
                        type_)


def _do_test_raw(data, path, should_fail=False, type_=None):
    filename = path.split("/")[-1]
    extension = filename.split(".")[-1]

    err = ErrorBundle()
    err.supported_versions = {}
    if type_:
        err.set_type(type_)

    parser = markuptester.MarkupParser(err, debug=True)
    parser.process(filename, data, extension)

    print err.print_summary(verbose=True)

    if should_fail:
        assert err.failed()
    else:
        assert not err.failed()

    return err


def test_local_url_detector():
    "Tests that local URLs can be detected."

    err = ErrorBundle()
    mp = markuptester.MarkupParser(err)
    tester = mp._is_url_local

    assert tester("chrome://xyz/content/abc")
    assert tester("chrome://whatever/")
    assert tester("local.xul")
    assert not tester("http://foo.bar/")
    assert not tester("https://abc.def/")

    assert tester(u"chrome://xyz/content/abc")
    assert tester(u"chrome://whatever/")
    assert tester(u"local.xul")
    assert not tester(u"http://foo.bar/")
    assert not tester(u"https://abc.def/")


def test_html_file():
    "Tests a package with a valid HTML file."

    _do_test("tests/resources/markup/markuptester/pass.html")


def test_xml_file():
    "Tests a package with a valid XML file."

    _do_test("tests/resources/markup/markuptester/pass.xml")


def test_xul_file():
    "Tests a package with a valid XUL file."
    _do_test("tests/resources/markup/markuptester/pass.xul")


def test_xml_bad_nesting():
    "Tests an XML file that has badly nested elements."
    _do_test("tests/resources/markup/markuptester/bad_nesting.xml", True)


def test_has_cdata():
    "Tests that CDATA is good to go."
    _do_test("tests/resources/markup/markuptester/cdata.xml")


def test_cdata_properly():
    """CDATA should be treated as text and be ignored by the parser."""

    err = _do_test_raw("""<foo>
    <script type="text/x-jquery-tmpl">
    <![CDATA[
    <button><p><span><foo>
    </bar></zap>
    <selfclosing />
    <><><><""><!><
    ]]>
    </script>
    </foo>""", "foo.xul", should_fail=False)

    # Test that there are no problems if the CDATA element starts or ends on
    # the same line as the parent tag.
    err = _do_test_raw("""<foo>
    <script><![CDATA[
    <button><p><span><foo>
    </bar></zap>
    <selfclosing />
    <><><><""><!><
    ]]></script>
    </foo>""", "foo.xul", should_fail=False)

    # Test that there are no problems if multiple CDATA elements open and
    # close on the same line.
    err = _do_test_raw("""<foo>
    <foo><![CDATA[</bar></foo>]]></foo><![CDATA[
    <![CDATA[ <-- Should be ignored since we're buffering.</bar><zap>
    ]]>
    </foo>""", "foo.xul", should_fail=False)

    err = _do_test_raw("""<foo>
    <![CDATA[
    <button><p><span><foo>
    </bar></zap>
    <selfclosing />
    <><><><""><!><
    ]]>
    </foo>""", "foo.xul", should_fail=False)

    err = _do_test_raw("""
    <![CDATA[
    <button><p><span><foo>
    </bar></zap>
    <selfclosing />
    <><><><""><!><
    ]]>""", "foo.xul", should_fail=False)


def test_xml_overclosing():
    "Tests an XML file that has overclosed elements"
    _do_test("tests/resources/markup/markuptester/overclose.xml", True)


def test_xml_extraclosing():
    "Tests an XML file that has extraclosed elements"
    _do_test("tests/resources/markup/markuptester/extraclose.xml", True)


def test_html_ignore_comment():
    "Tests that HTML comment values are ignored"
    _do_test("tests/resources/markup/markuptester/ignore_comments.html")


def test_html_css_style():
    "Tests that CSS within an element is passed to the CSS tester"
    _do_test("tests/resources/markup/markuptester/css_style.html", True)


def test_html_css_inline():
    "Tests that inline CSS is passed to the CSS tester"
    _do_test("tests/resources/markup/markuptester/css_inline.html", True)


def test_xul_evil():
    "Tests for evil kinds of scripts and iframes in XUL."
    _do_test("tests/resources/markup/markuptester/remote_src.xul", True)
    _do_test("tests/resources/markup/markuptester/bad_iframe_remote.xul", True)
    _do_test("tests/resources/markup/markuptester/bad_iframe_chrome.xul", True)
    _do_test("tests/resources/markup/markuptester/"
             "bad_iframe_remote_missing.xul",
             True)


def test_lp_passing():
    """Test a valid language pack or theme file."""
    _do_test("tests/resources/markup/markuptester/_langpack/lp_safe.html",
             False, PACKAGE_LANGPACK)
    _do_test("tests/resources/markup/markuptester/_langpack/lp_safe.html",
             False, PACKAGE_THEME)


def test_lp_unsafe():
    """Test a language pack or theme file that contains unsafe elements."""
    _do_test("tests/resources/markup/markuptester/_langpack/lp_unsafe.html",
             True, PACKAGE_LANGPACK)
    _do_test("tests/resources/markup/markuptester/_langpack/lp_unsafe.html",
             True, PACKAGE_THEME)


def test_lp_remote():
    """Test a language pack file that contains remote references."""
    _do_test("tests/resources/markup/markuptester/_langpack/lp_remote.html",
             True, PACKAGE_LANGPACK)
    _do_test("tests/resources/markup/markuptester/_langpack/lp_remote.html",
             True, PACKAGE_THEME)


def test_invalid_markup():
    "Tests an markup file that is simply broken."

    # Test for the banned test element
    _do_test("tests/resources/markup/markuptester/bad_banned.xml", True)

    result = _do_test("tests/resources/markup/markuptester/bad.xml", True)
    assert result.warnings
    result = _do_test("tests/resources/markup/markuptester/bad_script.xml",
                      False)
    assert result.notices


def test_bad_encoding():
    """Test that bad encodings don't cause the parser to fail."""
    _do_test("tests/resources/markup/encoding.txt")


def test_self_closing_scripts():
    """Tests that self-closing script tags are not deletrious to parsing."""
    _do_test_raw("""
    <foo>
        <script type="text/javascript"/>
        <list_item undecodable=" _ " />
        <list_item />
        <list_item />
    </foo>
    """, "foo.js")


def test_theme_attribute_prefixes():
    """Test that javascript and data URIs are flagged in themes."""

    _do_test_raw("""
    <foo><bar foo="http://bar" /></foo>
    """, "foo.js", type_=PACKAGE_THEME)

    _do_test_raw("""
    <foo><bar foo="data:bar" /></foo>
    """, "foo.js", type_=PACKAGE_THEME, should_fail=True)

    _do_test_raw("""
    <foo><bar foo="javascript:bar" /></foo>
    """, "foo.js", type_=PACKAGE_THEME, should_fail=True)


def test_theme_xbl():
    """Test that markup within script tags does not raise errors."""

    # Borrowed from http://bugs.python.org/file22767/hp_fix.diff
    _do_test_raw("""
    <script> <a href="" /> <p> <span></span> </p> </script>
    <script> foo = "</scr" + "ipt>"; </script>
    """, "foo.js", type_=PACKAGE_THEME)


def test_theme_xbl():
    """Test that themes ban a good chunk of XBL."""

    _do_test_raw("""
    <foo><xbl:foo /></foo>
    """, "foo.js", type_=PACKAGE_THEME)

    _do_test_raw("""
    <foo><xbl:constructor /></foo>
    """, "foo.js", type_=PACKAGE_THEME, should_fail=True)

    _do_test_raw("""
    <foo><xbl:property /></foo>
    """, "foo.js", type_=PACKAGE_THEME)

    _do_test_raw("""
    <foo><xbl:property onset="foo()" /></foo>
    """, "foo.js", type_=PACKAGE_THEME, should_fail=True)

    _do_test_raw("""
    <foo xmlns:xbl="http://www.mozilla.org/xbl">
        <property onset="" onget="" />
    </foo>
    """, "foo.js")

    _do_test_raw("""
    <foo xmlns:xbl="http://www.mozilla.org/xbl">
        <property onset="" onget="" />
    </foo>
    """, "foo.js", type_=PACKAGE_THEME, should_fail=True)


def test_dom_mutation():
    """Test that DOM mutation events are warned against."""

    _do_test_raw("""
    <foo><bar onzap="" /></foo>
    """, "foo.js")

    _do_test_raw("""
    <foo><bar ondomattrmodified="" /></foo>
    """, "foo.js", should_fail=True)


def test_dom_mutation():
    """Test that DOM mutation events are warned against."""

    _do_test_raw("""
    <foo><bar onzap="" /></foo>
    """, "foo.js")

    _do_test_raw("""
    <foo><bar ondomattrmodified="" /></foo>
    """, "foo.js", should_fail=True)

def test_proper_line_numbers():
    """Test that the proper line numbers are passed to test_js_snippet."""

    err = _do_test_raw("""<foo>
    <script>
    eval("OWOWOWOWOWOWOWOW");
    </script>
    </foo>""", "foo.xul", should_fail=True)

    assert err.warnings
    warning = err.warnings[0]
    eq_(warning["file"], "foo.xul")
    eq_(warning["line"], 3);


def test_script_scraping():
    """Test that the scripts in a document are collected properly."""

    err = ErrorBundle()
    err.supported_versions = {}
    parser = markuptester.MarkupParser(err, debug=True)
    parser.process("foo.xul", """
    <doc>
    <!-- One to be ignored -->
    <script type="text/javascript"></script>
    <script src="/relative.js"></script>
    <script src="chrome://namespace/absolute.js"></script>
    <script src="very_relative.js"></script>
    </doc>
    """, "xul")

    eq_(parser.found_scripts,
        set(["/relative.js", "chrome://namespace/absolute.js",
             "very_relative.js"]))

