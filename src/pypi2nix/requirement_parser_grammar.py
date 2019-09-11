from contextlib import contextmanager
from typing import no_type_check

from parsley import makeGrammar

from pypi2nix.environment_marker import EnvironmentMarker
from pypi2nix.environment_marker import MarkerToken
from pypi2nix.logger import ProxyLogger
from pypi2nix.requirements import PathRequirement
from pypi2nix.requirements import UrlRequirement
from pypi2nix.requirements import VersionRequirement


class _RequirementParserGrammar:
    """Do not instantiate this but import `requirement_parser_grammar` from this module."""

    @no_type_check
    def __init__(self) -> None:
        self._compiled_grammar = None
        self._logger = ProxyLogger()

    requirement_grammar = """
        wsp           = ' ' | '\t'
        version_cmp   = wsp* <'<=' | '<' | '!=' | '==' | '>=' | '>' | '~=' | '==='>
        version       = wsp* <( letterOrDigit | '-' | '_' | '.' | '*' | '+' | '!' )+>
        version_one   = version_cmp:op version:v wsp* -> (op, v)
        version_many  = version_one:v1 (wsp* ',' version_one)*:v2 -> [v1] + v2
        versionspec   = ('(' version_many:v ')' ->v) | version_many
        urlspec       = '@' wsp* <URI_reference>
        python_str_c  = (wsp | letter | digit | '(' | ')' | '.' | '{' | '}' |
                         '-' | '_' | '*' | '#' | ':' | ';' | ',' | '/' | '?' |
                         '[' | ']' | '!' | '~' | '`' | '@' | '$' | '%%' | '^' |
                         '&' | '=' | '+' | '|' | '<' | '>' )
        dquote        = '"'
        squote        = '\\''
        python_str    = (squote <(python_str_c | dquote)*>:s squote |
                         dquote <(python_str_c | squote)*>:s dquote) -> s
        env_var       = (%s | 'extra'
                         # ONLY when defined by a containing layer
                         ):varname -> lookup(varname)
        marker_var    = wsp* (env_var | python_str)
        marker_expr   = marker_var:l marker_op:o marker_var:r -> EnvironmentMarker(o, l, r)
                      | wsp* '(' marker:m wsp* ')' -> m
        marker_op     = version_cmp | (wsp* 'in') | (wsp* 'not' wsp+ 'in' -> 'not in')
        marker_and    = marker_expr:l wsp* 'and' marker_expr:r -> EnvironmentMarker('and', l, r)
                      | marker_expr:m -> m
        marker_or     = marker_and:l wsp* 'or' marker_and:r -> EnvironmentMarker('or', l, r)
                          | marker_and:m -> m
        marker        = marker_or
        quoted_marker = ';' wsp* marker
        identifier_end = letterOrDigit | (('-' | '_' | '.' )* letterOrDigit)
        identifier    = < letterOrDigit identifier_end* >
        name          = identifier
        extras_list   = identifier:i (wsp* ',' wsp* identifier)*:ids -> [i] + ids
        extras        = '[' wsp* extras_list?:e wsp* ']' -> e
        editable = '-e'
        egg_name = '#egg=' name:n -> n

        name_req      = (name:n wsp* extras?:e wsp* versionspec?:v wsp* quoted_marker?:m
                         -> VersionRequirement(name=n, extras=set(e or []), versions=v or [], environment_markers=m, logger=logger()))
        url_req       = name:n wsp* extras?:e wsp* urlspec:v (wsp+ | end) quoted_marker?:m
                        -> UrlRequirement(name=n, extras=set(e or []), url=v or [], environment_markers=m, logger=logger())
        path_req_pip_style = (editable wsp+)? <file_path>:path egg_name:name extras?:e (wsp* | end) quoted_marker?:marker
                             -> PathRequirement(name=name, path=path, environment_markers=marker, extras=set(e or []), logger=logger())
        url_req_pip_style = (editable wsp+)? <('hg+' | 'git+')? URI_reference_pip_style>:url egg_name:name extras?:e (wsp* | end) quoted_marker?:marker
                            -> UrlRequirement(name=name, url=url, extras=set(e or []), environment_markers=marker, logger=logger())
        specification = wsp* ( path_req_pip_style | url_req_pip_style | url_req | name_req ):s wsp* -> s

        file_path     = <('./' | '/')? file_path_segment ('/' file_path_segment)* '/'?>
        file_path_segment = file_path_segment_character+
        file_path_segment_character = ~('#'|'/') anything
        URI_reference = <URI | relative_ref>
        URI_reference_pip_style = <URI_pip_style | relative_ref>
        URI           = scheme ':' hier_part ('?' query )? ( '#' fragment)?
        URI_pip_style = scheme ':' hier_part ('?' query )?
        hier_part     = ('//' authority path_abempty) | path_absolute | path_rootless | path_empty
        absolute_URI  = scheme ':' hier_part ( '?' query )?
        relative_ref  = relative_part ( '?' query )? ( '#' fragment )?
        relative_part = '//' authority path_abempty | path_absolute | path_noscheme | path_empty
        scheme        = letter ( letter | digit | '+' | '-' | '.')*
        authority     = ( userinfo '@' )? host ( ':' port )?
        userinfo      = ( unreserved | pct_encoded | sub_delims | ':')*
        host          = IP_literal | IPv4address | reg_name
        port          = digit*
        IP_literal    = '[' ( IPv6address | IPvFuture) ']'
        IPvFuture     = 'v' hexdig+ '.' ( unreserved | sub_delims | ':')+
        IPv6address   = (
                          ( h16 ':'){6} ls32
                          | '::' ( h16 ':'){5} ls32
                          | ( h16 )?  '::' ( h16 ':'){4} ls32
                          | ( ( h16 ':')? h16 )? '::' ( h16 ':'){3} ls32
                          | ( ( h16 ':'){0,2} h16 )? '::' ( h16 ':'){2} ls32
                          | ( ( h16 ':'){0,3} h16 )? '::' h16 ':' ls32
                          | ( ( h16 ':'){0,4} h16 )? '::' ls32
                          | ( ( h16 ':'){0,5} h16 )? '::' h16
                          | ( ( h16 ':'){0,6} h16 )? '::' )
        h16           = hexdig{1,4}
        ls32          = ( h16 ':' h16) | IPv4address
        IPv4address   = dec_octet '.' dec_octet '.' dec_octet '.' dec_octet
        nz            = ~'0' digit
        dec_octet     = (
                          digit # 0-9
                          | nz digit # 10-99
                          | '1' digit{2} # 100-199
                          | '2' ('0' | '1' | '2' | '3' | '4') digit # 200-249
                          | '25' ('0' | '1' | '2' | '3' | '4' | '5') )# %%250-255
        reg_name = ( unreserved | pct_encoded | sub_delims)*
        path = (
                path_abempty # begins with '/' or is empty
                | path_absolute # begins with '/' but not '//'
                | path_noscheme # begins with a non-colon segment
                | path_rootless # begins with a segment
                | path_empty ) # zero characters
        path_abempty  = ( '/' segment)*
        path_absolute = '/' ( segment_nz ( '/' segment)* )?
        path_noscheme = segment_nz_nc ( '/' segment)*
        path_rootless = segment_nz ( '/' segment)*
        path_empty    = pchar{0}
        segment       = pchar*
        segment_nz    = pchar+
        segment_nz_nc = ( unreserved | pct_encoded | sub_delims | '@')+
                        # non-zero-length segment without any colon ':'
        pchar         = unreserved | pct_encoded | sub_delims | ':' | '@'
        query         = ( pchar | '/' | '?')*
        fragment      = ( pchar | '/' | '?')*
        pct_encoded   = '%%' hexdig
        unreserved    = letter | digit | '-' | '.' | '_' | '~'
        reserved      = gen_delims | sub_delims
        gen_delims    = ':' | '/' | '?' | '#' | '(' | ')?' | '@'
        sub_delims    = '!' | '$' | '&' | '\\'' | '(' | ')' | '*' | '+' | ',' | ';' | '='
        hexdig        = digit | 'a' | 'A' | 'b' | 'B' | 'c' | 'C' | 'd' | 'D' | 'e' | 'E' | 'f' | 'F'
    """ % (
        " | ".join(["'{}'".format(name.value) for name in MarkerToken]),
    )

    @no_type_check
    def _format_full_version(self, info) -> str:
        version = "{0.major}.{0.minor}.{0.micro}".format(info)
        kind = info.releaselevel
        if kind != "final":
            version += kind[0] + str(info.serial)
        return version

    @no_type_check
    def _environment_bindings(self, token):
        return MarkerToken.get_from_string(token)

    @no_type_check
    @contextmanager
    def __call__(self, logger):
        if self._compiled_grammar is None:
            self._compiled_grammar = makeGrammar(
                self.requirement_grammar,
                {
                    "lookup": self._environment_bindings,
                    "VersionRequirement": VersionRequirement,
                    "UrlRequirement": UrlRequirement,
                    "PathRequirement": PathRequirement,
                    "EnvironmentMarker": EnvironmentMarker,
                    "logger": lambda: self._logger.get_target_logger(),
                },
            )
            pass
        self._logger.set_target_logger(logger)
        yield self._compiled_grammar


requirement_parser_grammar = _RequirementParserGrammar()