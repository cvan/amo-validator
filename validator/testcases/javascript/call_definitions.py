import copy
import math
import types

import actions
import traverser as js_traverser
import predefinedentities
from jstypes import *
from validator.constants import BUGZILLA_BUG
from validator.decorator import version_range

# Function prototypes should implement the following:
#  wrapper : The JSWrapper instace that is being called
#  arguments : A list of argument nodes; untraversed
#  traverser : The current traverser object


def amp_rp_bug660359(wrapper, arguments, traverser):
    """
    Flag all calls to AddonManagerPrivate.registerProvider for incompatibility
    with Firefox 6.
    """

    traverser.err.notice(
        err_id=("testcases_javascript_calldefinitions",
                "amp_rp_bug660359"),
        notice="Custom add-on types may not work properly in Firefox 6",
        description="This add-on appears to register custom add-on types, "
                    "which are affected and may not work properly due to "
                    "changes made on Firefox 6. For more information, "
                    "please refer to "
                    "https://bugzilla.mozilla.org/show_bug.cgi?id=595848",
        filename=traverser.filename,
        line=traverser.line,
        column=traverser.position,
        context=traverser.context,
        for_appversions={'{ec8030f7-c20a-464f-9b0e-13a3a9e97384}':
                             version_range("firefox", "6.0a1", "7.0a1"),
                         '{3550f703-e582-4d05-9a08-453d09bdfdc6}':
                             version_range("thunderbird", "6.0a1", "7.0a1"),},
        compatibility_type="error",
        tier=5)


def xpcom_constructor(method, extend=False, mutate=False, pretraversed=False):
    """Returns a function which wraps an XPCOM class instantiation function."""

    def definition(wrapper, arguments, traverser):
        """Wraps an XPCOM class instantiation function."""

        if not arguments:
            return None

        traverser._debug("(XPCOM Encountered)")

        if not pretraversed:
            arguments = [traverser._traverse_node(x) for x in arguments]
        argz = arguments[0]

        if not argz.is_global or "xpcom_map" not in argz.value:
            argz = JSWrapper(traverser=traverser)
            argz.value = {"xpcom_map": lambda: {"value": {}}}

        traverser._debug("(Building XPCOM...)")

        inst = traverser._build_global(method,
                                       copy.deepcopy(argz.value["xpcom_map"]()))
        inst.value["overwritable"] = True

        if extend or mutate:
            # FIXME: There should be a way to get this without
            # traversing the call chain twice.
            parent = actions.trace_member(traverser, wrapper["callee"]["object"])

            if mutate and not (parent.is_global and
                               isinstance(parent.value, dict) and
                               "value" in parent.value):
                # Assume that the parent object is a first class
                # wrapped native
                parent.value = inst.value

                # FIXME: Only objects marked as global are processed
                # as XPCOM instances
                parent.is_global = True

            if isinstance(parent.value, dict):
                if extend and mutate:
                    if callable(parent.value["value"]):
                        parent.value["value"] = \
                            copy.deepcopy(parent.value["value"](t=traverser))

                    parent.value["value"].update(inst.value["value"])
                    return parent

                if extend:
                    inst.value["value"].update(parent.value["value"])

                if mutate:
                    parent.value = inst.value

        return inst
    definition.__name__ = "xpcom_%s" % str(method)
    return definition


# Global object function definitions:
def string_global(wrapper, arguments, traverser):
    if not arguments:
        return JSWrapper("", traverser=traverser)
    arg = traverser._traverse_node(arguments[0])
    value = actions._get_as_str(arg.get_literal_value())
    return JSWrapper(value, traverser=traverser)


def array_global(wrapper, arguments, traverser):
    output = JSArray()
    if arguments:
        output.elements = [traverser._traverse_node(a) for a in arguments]
    return JSWrapper(output, traverser=traverser)


def number_global(wrapper, arguments, traverser):
    if not arguments:
        return JSWrapper(0, traverser=traverser)
    arg = traverser._traverse_node(arguments[0])
    try:
        value = float(arg.get_literal_value())
    except (ValueError, TypeError):
        return traverser._build_global(
                name="NaN",
                entity=predefinedentities.GLOBAL_ENTITIES[u"NaN"])
    return JSWrapper(value, traverser=traverser)


def boolean_global(wrapper, arguments, traverser):
    if not arguments:
        return JSWrapper(False, traverser=traverser)
    arg = traverser._traverse_node(arguments[0])
    return JSWrapper(bool(arg.get_literal_value()), traverser=traverser)


def python_wrap(func, args, nargs=False):
    """
    This is a helper function that wraps Python functions and exposes them to
    the JS engine. The first parameter should be the Python function to wrap.
    The second parameter should be a list of tuples. Each tuple should
    contain:

     1. The type of value to expect:
        - "string"
        - "num"
     2. A default value.
    """

    def _process_literal(type_, literal):
        if type_ == "string":
            return actions._get_as_str(literal)
        elif type_ == "num":
            return actions._get_as_num(literal)
        return literal

    def wrap(wrapper, arguments, traverser):
        passed_args = [traverser._traverse_node(a) for a in arguments]

        params = []
        if not nargs:
            # Handle definite argument lists.
            for type_, def_value in args:
                if passed_args:
                    parg = passed_args[0]
                    passed_args = passed_args[1:]

                    passed_literal = parg.get_literal_value()
                    passed_literal = _process_literal(type_, passed_literal)
                    params.append(passed_literal)
                else:
                    params.append(def_value)
        else:
            # Handle dynamic argument lists.
            for arg in passed_args:
                literal = arg.get_literal_value()
                params.append(_process_literal(args[0], literal))

        traverser._debug("Calling wrapped Python function with: (%s)" %
                             ", ".join(map(str, params)))
        try:
            output = func(*params)
        except:
            # If we cannot compute output, just return nothing.
            output = None

        return JSWrapper(output, traverser=traverser)

    return wrap


def math_log(wrapper, arguments, traverser):
    """Return a better value than the standard python log function."""
    args = [traverser._traverse_node(a) for a in arguments]
    if not args:
        return JSWrapper(0, traverser=traverser)

    arg = actions._get_as_num(args[0].get_literal_value())
    if arg == 0:
        return JSWrapper(float('-inf'), traverser=traverser)

    if arg < 0:
        return JSWrapper(traverser=traverser)

    arg = math.log(arg)
    return JSWrapper(arg, traverser=traverser)


def math_random(wrapper, arguments, traverser):
    """Return a "random" value for Math.random()."""
    return JSWrapper(0.5, traverser=traverser)


def math_round(wrapper, arguments, traverser):
    """Return a better value than the standard python round function."""
    args = [traverser._traverse_node(a) for a in arguments]
    if not args:
        return JSWrapper(0, traverser=traverser)

    arg = actions._get_as_num(args[0].get_literal_value())
    # Prevent nasty infinity tracebacks.
    if abs(arg) == float("inf"):
        return args[0]

    # Python rounds away from zero, JS rounds "up".
    if arg < 0 and int(arg) != arg:
        arg += 0.0000000000000001
    arg = round(arg)
    return JSWrapper(arg, traverser=traverser)


def nsIDOMFile_deprec(wrapper, arguments, traverser):
    """Throw a compatibility error about removed XPCOM methods."""
    traverser.err.notice(
        err_id=("testcases_javascript_calldefinitions", "nsIDOMFile",
                "deprec"),
        notice="Deprecated nsIDOMFile methods in use.",
        description=("Your add-on uses methods that have been removed from "
                     "the nsIDOMFile interface in Firefox 7. Please refer to "
                     "%s for more information.") % (BUGZILLA_BUG % 661876),
        filename=traverser.filename,
        line=traverser.line,
        column=traverser.position,
        context=traverser.context,
        compatibility_type="error",
        for_appversions={'{ec8030f7-c20a-464f-9b0e-13a3a9e97384}':
                             version_range("firefox", "7.0a1", "8.0a1"),
                         '{3550f703-e582-4d05-9a08-453d09bdfdc6}':
                             version_range("thunderbird", "7.0a1", "8.0a1"),},
        tier=5)

    return JSWrapper(JSObject(), traverser=traverser)


def nsIJSON_deprec(wrapper, arguments, traverser):
    """Throw a compatibility error about removed XPCOM methods."""
    traverser.err.notice(
        err_id=("testcases_javascript_calldefinitions", "nsIJSON",
                "deprec"),
        notice="Deprecated nsIJSON methods in use.",
        description=("The encode and decode methods in nsIJSON have been "
                     "deprecated in Firefox 7. You can use the methods in the "
                     "global JSON object instead. See %s for more "
                     "information.") %
                         "https://developer.mozilla.org/En/Using_native_JSON",
                    #"%s for more information.") % (BUGZILLA_BUG % 645922),
        filename=traverser.filename,
        line=traverser.line,
        column=traverser.position,
        context=traverser.context,
        compatibility_type="warning",
        for_appversions={'{ec8030f7-c20a-464f-9b0e-13a3a9e97384}':
                             version_range("firefox", "7.0a1", "8.0a1"),
                         '{3550f703-e582-4d05-9a08-453d09bdfdc6}':
                             version_range("thunderbird", "7.0a1", "8.0a1"),},
        tier=5)

    return JSWrapper(JSObject(), traverser=traverser)

def nsIImapMailFolderSink_changed(wrapper, arguments, traverser):
    """Flag calls to nsIImapMailFolderSink for possible incompatibility with Thunderbird 6"""
    traverser.err.notice(
        err_id=("testcases_javascript_calldefinitions", "nsIImapMailFolderSink"),
        notice="Modified nsIImapMailFolderSink method in use.",
        description="This add-on appears to use nsIImapMailFolderSink.setUrlState, "
                    "which may no longer work correctly due to  "
                    "changes made in Thunderbird 6. For more information, "
                    "please refer to "
                    "https://bugzilla.mozilla.org/show_bug.cgi?id=464126",
        filename=traverser.filename,
        line=traverser.line,
        column=traverser.position,
        context=traverser.context,
        compatibility_type="error",
        for_appversions={'{3550f703-e582-4d05-9a08-453d09bdfdc6}':
                             version_range("thunderbird", "6.0a1", "8.0a1")},
        tier=5)

    return JSWrapper(JSObject(), traverser=traverser)

def nsIImapProtocol_removed(wrapper, arguments, traverser):
    """Flag calls to nsIImapProtocol for incompatibility with Thunderbird 6"""
    traverser.err.notice(
        err_id=("testcases_javascript_calldefinitions", "nsIImapProtocol"),
        notice="Removed nsIImapProtocol method in use.",
        description="This add-on appears to use nsIImapProtocol.NotifyHdrsToDownload, "
                    "which may no longer work correctly due to  "
                    "changes made in Thunderbird 6. For more information, "
                    "please refer to "
                    "https://bugzilla.mozilla.org/show_bug.cgi?id=464126",
        filename=traverser.filename,
        line=traverser.line,
        column=traverser.position,
        context=traverser.context,
        compatibility_type="error",
        for_appversions={'{3550f703-e582-4d05-9a08-453d09bdfdc6}':
                             version_range("thunderbird", "6.0a1", "8.0a1")},
        tier=5)

    return JSWrapper(JSObject(), traverser=traverser)


def document_getSelection(wrapper, arguments, traverser):
    """Flag Firefox 8 calls to document.getSelection()."""

    MDN_ARTICLE = "https://developer.mozilla.org/En/Window.getSelection"

    traverser.err.notice(
        err_id=("testcases_javascript_calldefinitions", "document_getSel"),
        notice="document.getSelection()'s return type has changed.",
        description="The return type of document.getSelection() has changed "
                    "in Firefox 8. This function is deprecated, and you "
                    "should be using window.getSelection() instead. See "
                    "%s for more information." % MDN_ARTICLE,
        filename=traverser.filename,
        line=traverser.line,
        column=traverser.position,
        context=traverser.context,
        compatibility_type="error",
        for_appversions={'{ec8030f7-c20a-464f-9b0e-13a3a9e97384}':
                             version_range("firefox", "8.0a1", "9.0a1"),
                         '{3550f703-e582-4d05-9a08-453d09bdfdc6}':
                             version_range("thunderbird", "8.0a1", "9.0a1"),},
        tier=5)

    # The new spec returns an object.
    return JSWrapper(JSObject(), traverser=traverser)


def nsIMsgThread_removed(wrapper, arguments, traverser):
    """Flag calls to nsIMsgThread for incompatibility with Thunderbird 7"""
    traverser.err.notice(
        err_id=("testcases_javascript_calldefinitions", "nsIMsgThread"),
        notice="Removed nsIMsgThread method in use.",
        description="This add-on appears to use nsIMsgThread.GetChildAt, "
                    "which may no longer work correctly due to  "
                    "changes made in Thunderbird 7. For more information, "
                    "please refer to "
                    "https://bugzilla.mozilla.org/show_bug.cgi?id=617839",
        filename=traverser.filename,
        line=traverser.line,
        column=traverser.position,
        context=traverser.context,
        compatibility_type="error",
        for_appversions={'{3550f703-e582-4d05-9a08-453d09bdfdc6}':
                             version_range("thunderbird", "7.0a1", "8.0a1")},
        tier=5)

    return JSWrapper(JSObject(), traverser=traverser)


def mail_attachment_api(wrapper, arguments, traverser):
    """Flag calls to the global attachment functions for incompatibility with Thunderbird 7"""
    traverser.err.notice(
        err_id=("testcases_javascript_calldefinitions", "AttachmentAPI"),
        notice="Removed attachment API function in use.",
        description="This add-on appears to use a global attachment function, one of: "
                    "attachmentIsEmpty, cloneAttachment, createNewAttachmentInfo "
                    "detachAttachment, openAttachment or saveAttachment, "
                    "which were removed in Thunderbird 7. For more information, "
                    "please refer to "
                    "https://bugzilla.mozilla.org/show_bug.cgi?id=657856",
        filename=traverser.filename,
        line=traverser.line,
        column=traverser.position,
        context=traverser.context,
        compatibility_type="error",
        for_appversions={'{3550f703-e582-4d05-9a08-453d09bdfdc6}':
                             version_range("thunderbird", "7.0a1", "8.0a1")},
        tier=5)

    return JSWrapper(JSObject(), traverser=traverser)


def nsIMsgSearchScopeTerm_removed(wrapper, arguments, traverser):
    """Flag calls to nsIMsgSearchScopeTerm methods for incompatibility with Thunderbird 8"""
    traverser.err.notice(
        err_id=("testcases_javascript_calldefinitions", "nsIMsgSearchScopeTerm"),
        notice="Removed nsIMsgSearchScopeTerm method in use.",
        description="This add-on appears to use nsIMsgSearchScopeTerm.mailFile or, "
                    "nsIMsgSearchScopeTerm.inputStream, both of which have been removed"
                    "as part of changes made in Thunderbird 8. For more information, "
                    "please refer to "
                    "https://bugzilla.mozilla.org/show_bug.cgi?id=668700",
        filename=traverser.filename,
        line=traverser.line,
        column=traverser.position,
        context=traverser.context,
        compatibility_type="error",
        for_appversions={'{3550f703-e582-4d05-9a08-453d09bdfdc6}':
                             version_range("thunderbird", "8.0a1", "9.0a1")},
        tier=5)

    return JSWrapper(JSObject(), traverser=traverser)

