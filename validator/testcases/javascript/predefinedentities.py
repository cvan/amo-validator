import math

import actions
from actions import _get_as_str
import call_definitions
from call_definitions import xpcom_constructor as xpcom_const, python_wrap
from jstypes import JSWrapper

# A list of identifiers and member values that may not be used.
BANNED_IDENTIFIERS = {
    u"newThread": "Creating threads from JavaScript is a common cause "
                  "of crashes and is unsupported in recent versions of the platform",
    u"processNextEvent": "Spinning the event loop with processNextEvent is a common "
                         "cause of deadlocks, crashes, and other errors due to "
                         "unintended reentrancy. Please use asynchronous callbacks "
                         "instead wherever possible",
}

BANNED_PREF_BRANCHES = [
    u"browser.preferences.instantApply",
    u"capability.policy.",
    u"extensions.alwaysUnpack",
    u"extensions.blocklist.",
    u"extensions.bootstrappedAddons",
    u"extensions.checkCompatibility",
    u"extensions.dss.",
    u"extensions.getAddons.",
    u"extensions.getMoreThemesURL",
    u"extensions.installCache",
    u"extensions.lastAppVersion",
    u"extensions.pendingOperations",
    u"extensions.update.",
    u"general.useragent.",
    u"network.http.",
    u"network.websocket.",
]

BANNED_PREF_REGEXPS = [
    r"extensions\..*\.update\.(url|enabled|interval)",
]

# See https://github.com/mattbasta/amo-validator/wiki/JS-Predefined-Entities
# for details on entity properties.

CONTENT_DOCUMENT = None

INTERFACES = {
    u"nsICategoryManager":
        {"value":
            {u"addCategoryEntry":
                {"dangerous":
                    lambda a, t, e:
                        e.get_resource("em:bootstrap") and \
                        ("Bootstrapped add-ons may not create persistent "
                         "category entries"
                         if a and len(a) > 3 and t(a[3]).get_literal_value()
                         else
                         "Authors of bootstrapped add-ons must take care "
                         "to cleanup any added category entries "
                         "at shutdown")}}},
    u"nsIAccessibleRetrieval":
        {"dangerous":
            "Using the nsIAccessibleRetrieval interface causes significant "
            "performance degradation in Firefox. It should only be used in "
            "accessibility-related add-ons."},
    u"nsIComponentRegistrar":
        {"value":
            {u"autoRegister":
                {"dangerous":
                    lambda a, t, e:
                        e.get_resource("em:bootstrap") and \
                        "Bootstrapped add-ons may not register "
                        "chrome manifest files"},
             u"registerFactory":
                {"dangerous":
                    lambda a, t, e:
                        e.get_resource("em:bootstrap") and \
                        "Authors of bootstrapped add-ons must take care "
                        "to cleanup any component registrations "
                        "at shutdown"}}},
    u"nsIJSON":
        {"value":
            {u"encode":
                {"return": call_definitions.nsIJSON_deprec},
             u"decode":
                {"return": call_definitions.nsIJSON_deprec}}},
    u"nsIImapMailFolderSink":
        {"value":
            {u"setUrlState":
                {"return": call_definitions.nsIImapMailFolderSink_changed}}},
    u"nsIImapProtocol":
        {"value":
            {u"NotifyHdrsToDownload":
                {"return": call_definitions.nsIImapProtocol_removed}}},
    u"nsIMsgSearchScopeTerm":
        {"value":
            {u"mailFile":
                {"return": call_definitions.nsIMsgSearchScopeTerm_removed},
             u"inputStream":
                {"return": call_definitions.nsIMsgSearchScopeTerm_removed}}},
    u"nsIMsgThread":
        {"value":
            {u"GetChildAt":
                {"return": call_definitions.nsIMsgThread_removed}}},
    u"nsIObserverService":
        {"value":
            {u"addObserver":
                {"dangerous":
                    lambda a, t, e:
                        e.get_resource("em:bootstrap") and \
                        "Authors of bootstrapped add-ons must take care "
                        "to remove any added observers "
                        "at shutdown"}}},
    u"nsIResProtocolHandler":
        {"value":
            {u"setSubstitution":
                {"dangerous":
                    lambda a, t, e:
                        e.get_resource("em:bootstrap") and \
                        a and \
                        len(a) > 1 and  \
                        t(a[1]).get_literal_value() and \
                        "Authors of bootstrapped add-ons must take care "
                        "to cleanup any added resource substitutions "
                        "at shutdown"}}},
    u"nsIStringBundleService":
        {"value":
            {u"createStringBundle":
                {"dangerous":
                    lambda a, t, e:
                        e.get_resource("em:bootstrap") and \
                        "Authors of bootstrapped add-ons must take care "
                        "to flush the string bundle cache at shutdown"},
             u"createExtensibleBundle":
                {"dangerous":
                    lambda a, t, e:
                        e.get_resource("em:bootstrap") and \
                        "Authors of bootstrapped add-ons must take care "
                        "to flush the string bundle cache at shutdown"}}},
    u"nsIStyleSheetService":
        {"value":
            {u"loadAndRegisterSheet":
                {"dangerous":
                    lambda a, t, e:
                        e.get_resource("em:bootstrap") and \
                        "Authors of bootstrapped add-ons must take care "
                        "to unregister any registered stylesheets "
                        "at shutdown"}}},
    u"nsIWindowMediator":
        {"value":
            {"registerNotification":
                {"dangerous":
                    lambda a, t, e:
                        e.get_resource("em:bootstrap") and \
                        "Authors of bootstrapped add-ons must take care "
                        "to remove any added observers "
                        "at shutdown"}}},
    u"nsIWindowWatcher":
        {"value":
            {u"addListener":
                {"dangerous":
                    lambda a, t, e:
                        e.get_resource("em:bootstrap") and \
                        "Authors of bootstrapped add-ons must take care "
                        "to remove any added observers "
                        "at shutdown"}}},
    }


def build_quick_xpcom(method, interface, traverser):
    """A shortcut to quickly build XPCOM objects on the fly."""
    constructor = xpcom_const(method, pretraversed=True)
    interface_obj = traverser._build_global(
                        name=method,
                        entity={"xpcom_map": lambda: INTERFACES[interface]})
    object = constructor(None, [interface_obj], traverser)
    if isinstance(object, JSWrapper):
        object = object.value
    return object


# GLOBAL_ENTITIES is also representative of the `window` object.
GLOBAL_ENTITIES = {
    u"window": {"value": lambda t: {"value": GLOBAL_ENTITIES}},
    u"null": {"literal": lambda t: JSWrapper(None, traverser=t)},
    u"Cc": {"readonly": False,
            "value":
                lambda t: GLOBAL_ENTITIES["Components"]["value"]["classes"]},
    u"Ci": {"readonly": False,
            "value":
                lambda t: GLOBAL_ENTITIES["Components"]["value"]["interfaces"]},

    u"Cu": {"readonly": False,
            "value":
                lambda t: GLOBAL_ENTITIES["Components"]["value"]["utils"]},
    u"Services":
        {"value": {u"scriptloader": {"dangerous": True},
                   u"wm":
                       {"value":
                            lambda t: build_quick_xpcom("getService",
                                                        "nsIWindowMediator",
                                                        t)},
                   u"ww":
                       {"value":
                            lambda t: build_quick_xpcom("getService",
                                                        "nsIWindowWatcher",
                                                        t)}}},

    u"document":
        {"value":
             {u"title":
                  {"overwriteable": True,
                   "readonly": False},
              u"defaultView":
                  {"value": lambda t: {"value": GLOBAL_ENTITIES}},
              u"createElement":
                  {"dangerous":
                       lambda a, t, e:
                           not a or
                           unicode(t(a[0]).get_literal_value()).lower() ==
                               "script"},
              u"createElementNS":
                  {"dangerous":
                       lambda a, t, e:
                           not a or
                           unicode(t(a[0]).get_literal_value()).lower() ==
                               "script"},
              u"getSelection":
                  {"return": call_definitions.document_getSelection},
              u"loadOverlay":
                  {"dangerous":
                       lambda a, t, e:
                           not a or
                           not unicode(t(a[0]).get_literal_value()).lower()
                               .startswith(("chrome:", "resource:"))}}},

    # The nefariuos timeout brothers!
    u"setTimeout": {"dangerous": actions._call_settimeout},
    u"setInterval": {"dangerous": actions._call_settimeout},
    
    # mail Attachment API Functions 
    u"createNewAttachmentInfo": {"return": call_definitions.mail_attachment_api},
    u"saveAttachment": {"return": call_definitions.mail_attachment_api},
    u"attachmentIsEmpty": {"return": call_definitions.mail_attachment_api},
    u"openAttachment": {"return": call_definitions.mail_attachment_api},
    u"detachAttachment": {"return": call_definitions.mail_attachment_api},
    u"cloneAttachment": {"return": call_definitions.mail_attachment_api},
        
    u"encodeURI": {"readonly": True},
    u"decodeURI": {"readonly": True},
    u"encodeURIComponent": {"readonly": True},
    u"decodeURIComponent": {"readonly": True},
    u"escape": {"readonly": True},
    u"unescape": {"readonly": True},
    u"isFinite": {"readonly": True},
    u"isNaN": {"readonly": True},
    u"parseFloat": {"readonly": True},
    u"parseInt": {"readonly": True},

    u"eval": {"dangerous": True},

    u"Function": {"dangerous": True},
    u"Object":
        {"value":
             {u"prototype": {"readonly": True},
              u"constructor":  # Just an experiment for now
                  {"value": lambda t: GLOBAL_ENTITIES["Function"]}}},
    u"String":
        {"value":
             {u"prototype": {"readonly": True}},
         "return": call_definitions.string_global},
    u"Array":
        {"value":
             {u"prototype": {"readonly": True}},
         "return": call_definitions.array_global},
    u"Number":
        {"value":
             {u"prototype":
                  {"readonly": True},
              u"POSITIVE_INFINITY":
                  {"value": lambda t: JSWrapper(float('inf'), traverser=t)},
              u"NEGATIVE_INFINITY":
                  {"value": lambda t: JSWrapper(float('-inf'), traverser=t)}},
         "return": call_definitions.number_global},
    u"Boolean":
        {"value":
             {u"prototype": {"readonly": True}},
         "return": call_definitions.boolean_global},
    u"RegExp": {"value": {u"prototype": {"readonly": True}}},
    u"Date": {"value": {u"prototype": {"readonly": True}}},

    u"Math":
        {"value":
             {u"PI":
                  {"value": lambda t: JSWrapper(math.pi, traverser=t)},
              u"E":
                  {"value": lambda t: JSWrapper(math.e, traverser=t)},
              u"LN2":
                  {"value": lambda t: JSWrapper(math.log(2), traverser=t)},
              u"LN10":
                  {"value": lambda t: JSWrapper(math.log(10), traverser=t)},
              u"LOG2E":
                  {"value": lambda t: JSWrapper(math.log(math.e, 2),
                                                traverser=t)},
              u"LOG10E":
                  {"value": lambda t: JSWrapper(math.log10(math.e),
                                                traverser=t)},
              u"SQRT2":
                  {"value": lambda t: JSWrapper(math.sqrt(2), traverser=t)},
              u"SQRT1_2":
                  {"value": lambda t: JSWrapper(math.sqrt(1/2), traverser=t)},
              u"abs":
                  {"return": python_wrap(abs, [("num", 0)])},
              u"acos":
                  {"return": python_wrap(math.acos, [("num", 0)])},
              u"asin":
                  {"return": python_wrap(math.asin, [("num", 0)])},
              u"atan":
                  {"return": python_wrap(math.atan, [("num", 0)])},
              u"atan2":
                  {"return": python_wrap(math.atan2, [("num", 0),
                                                      ("num", 1)])},
              u"ceil":
                  {"return": python_wrap(math.ceil, [("num", 0)])},
              u"cos":
                  {"return": python_wrap(math.cos, [("num", 0)])},
              u"exp":
                  {"return": python_wrap(math.exp, [("num", 0)])},
              u"floor":
                  {"return": python_wrap(math.floor, [("num", 0)])},
              u"log":
                  {"return": call_definitions.math_log},
              u"max":
                  {"return": python_wrap(max, [("num", 0)], nargs=True)},
              u"min":
                  {"return": python_wrap(min, [("num", 0)], nargs=True)},
              u"pow":
                  {"return": python_wrap(math.pow, [("num", 0),
                                                    ("num", 0)])},
              u"random": # Random always returns 0.5 in our fantasy land.
                  {"return": call_definitions.math_random},
              u"round":
                  {"return": call_definitions.math_round},
              u"sin":
                  {"return": python_wrap(math.sin, [("num", 0)])},
              u"sqrt":
                  {"return": python_wrap(math.sqrt, [("num", 1)])},
              u"tan":
                  {"return": python_wrap(math.tan, [("num", 0)])},
                  }},

    u"netscape":
        {"value":
             {u"security":
                  {"value":
                       {u"PrivilegeManager":
                            {"value":
                                 {u"enablePrivilege":
                                      {"dangerous": True}}}}}}},

    u"navigator":
        {"value": {u"wifi": {"dangerous": True},
                   u"geolocation": {"dangerous": True}}},

    u"Components":
        {"readonly": True,
         "value":
             {u"classes":
                  {"xpcom_wildcard": True,
                   "value":
                       {u"createInstance":
                           {"return": xpcom_const("createInstance")},
                        u"getService":
                           {"return": xpcom_const("getService")}}},
              "utils":
                  {"value": {u"evalInSandbox":
                                 {"dangerous": True},
                             u"import":
                                 {"dangerous":
                                      lambda a, t, e:
                                        a and
                                        _get_as_str(t(a[0]).get_literal_value())
                                            .count("ctypes.jsm")}}},
              u"interfaces":
                  {"value": {u"nsIXMLHttpRequest":
                                {"xpcom_map":
                                     lambda:
                                        GLOBAL_ENTITIES["XMLHttpRequest"]},
                             u"nsIAccessibleRetrieval":
                                {"xpcom_map":
                                     lambda:
                                        INTERFACES["nsIAccessibleRetrieval"]},
                             u"nsICategoryManager":
                                {"xpcom_map":
                                     lambda:
                                        INTERFACES["nsICategoryManager"]},
                             u"nsIComponentRegistrar":
                                {"xpcom_map":
                                     lambda:
                                        INTERFACES["nsIComponentRegistrar"]},
                             u"nsIJSON":
                                {"xpcom_map":
                                     lambda:
                                        INTERFACES["nsIJSON"]},
                             u"nsIImapMailFolderSink":
                                {"xpcom_map":
                                     lambda:
                                        INTERFACES["nsIImapMailFolderSink"]},
                             u"nsIImapProtocol":
                                {"xpcom_map":
                                     lambda:
                                        INTERFACES["nsIImapProtocol"]},
                             u"nsIMsgSearchScopeTerm":
                                {"xpcom_map":
                                     lambda:
                                        INTERFACES["nsIMsgSearchScopeTerm"]},
                             u"nsIMsgThread":
                                {"xpcom_map":
                                     lambda:
                                        INTERFACES["nsIMsgThread"]},
                             u"nsIObserverService":
                                {"xpcom_map":
                                     lambda:
                                        INTERFACES["nsIObserverService"]},
                             u"nsIResProtocolHandler":
                                {"xpcom_map":
                                     lambda:
                                        INTERFACES["nsIResProtocolHandler"]},
                             u"nsIStringBundleService":
                                {"xpcom_map":
                                     lambda:
                                        INTERFACES["nsIStringBundleService"]},
                             u"nsIStyleSheetService":
                                {"xpcom_map":
                                     lambda:
                                        INTERFACES["nsIStyleSheetService"]},
                             u"nsIWindowMediator":
                                {"xpcom_map":
                                     lambda:
                                        INTERFACES["nsIWindowMediator"]},
                             u"nsIWindowWatcher":
                                {"xpcom_map":
                                     lambda:
                                        INTERFACES["nsIWindowWatcher"]},
                             u"nsIProcess":
                                {"dangerous": True},
                             u"nsIDOMGeoGeolocation":
                                {"dangerous": True},
                             u"nsIX509CertDB":
                                {"dangerous": True},
                             u"mozIJSSubScriptLoader":
                                {"dangerous": True}}}}},
    u"extensions": {"dangerous": True},
    u"xpcnativewrappers": {"dangerous": True},

    u"AddonManagerPrivate":
        {"value":
            {u"registerProvider": {"return": call_definitions.amp_rp_bug660359}}},

    u"XMLHttpRequest":
        {"value":
             {u"open":
                  {"dangerous":
                       # Ban syncrhonous XHR by making sure the third arg
                       # is absent and false.
                       lambda a, t, e:
                           a and len(a) >= 3 and
                           not t(a[2]).get_literal_value() and
                           "Synchronous HTTP requests can cause serious UI "
                           "performance problems, especially to users with "
                           "slow network connections."}}},

    # Global properties are inherently read-only, though this formalizes it.
    u"Infinity":
        {"readonly": True,
         "value":
             lambda t:
                 GLOBAL_ENTITIES[u"Number"]["value"][u"POSITIVE_INFINITY"]},
    u"NaN": {"readonly": True},
    u"undefined": {"readonly": True},

    u"innerHeight": {"readonly": False},
    u"innerWidth": {"readonly": False},
    u"width": {"readonly": False},
    u"height": {"readonly": False},
    u"top": {"readonly": actions._readonly_top},

    u"content":
        {"context": "content",
         "value":
             {u"document":
                  {"value": lambda t: GLOBAL_ENTITIES[u"document"]}}},
    u"contentWindow":
        {"context": "content",
         "value":
             lambda t: {"value": GLOBAL_ENTITIES}},
    u"_content": {"value": lambda t: GLOBAL_ENTITIES[u"content"]},
    u"gBrowser":
        {"value":
             {u"contentDocument":
                  {"context": "content",
                   "value": lambda t: CONTENT_DOCUMENT},
              u"contentWindow":
                  {"value":
                       lambda t: {"value": GLOBAL_ENTITIES}}}},
    u"opener":
        {"value":
             lambda t: {"value": GLOBAL_ENTITIES}},

    # Preference creation in pref defaults files
    u"pref": {"dangerous": actions._call_create_pref},
    u"user_pref": {"dangerous": actions._call_create_pref},
}

CONTENT_DOCUMENT = GLOBAL_ENTITIES[u"content"]["value"][u"document"]

