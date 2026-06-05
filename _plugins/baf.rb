# frozen_string_literal: true

# Rouge lexer for WeiDU BAF, the Infinity Engine compiled-script source shown throughout the IESDP
# scripting docs. Registered under the `baf` tag, so kramdown highlights ```baf fenced blocks at build time.
#
# Highlighting is deliberately structural. The upstream BGforge-MLS TextMate grammar ships ~380 KB of IDS
# keyword lists, but every one of those lists resolves to a single scope (constant.other), and the only
# further distinction it draws is action-functions vs trigger-functions. Both are reproduced here from
# structure alone: an all-caps bareword is a constant, and a name directly before "(" is a function coloured
# by context - a trigger inside an IF...THEN condition, an action inside a RESPONSE...END block. So there are
# no keyword tables to carry and nothing to re-sync when the upstream IDS lists grow.

require 'rouge'

module Rouge
  module Lexers
    class Baf < RegexLexer
      title 'BAF'
      desc 'WeiDU BAF (Infinity Engine script source)'
      tag 'baf'
      filenames '*.baf'

      # Shared lexical atoms: comments, strings, literals, variables, operators, constants. Anything that is
      # not a structural keyword (IF/THEN/RESPONSE/END) or a function call lives here.
      state :content do
        rule %r{//.*}, Comment::Single
        rule %r{/\*}, Comment::Multiline, :comment_block
        rule %r/\s+/, Text::Whitespace
        rule %r/"/, Str::Double, :string
        rule %r/(@)(\d+)/ do                            # tra reference, e.g. @123
          groups Keyword, Name::Variable
        end
        rule %r/%[^%]+%/, Name::Variable                # %variable% substitution
        rule %r/\b0x[0-9a-fA-F]+\b/, Num::Hex
        rule %r/\b\d+\b/, Num::Integer
        rule %r/\bOR\b/, Operator::Word
        rule %r/!/, Operator
        rule %r/\b[A-Z][A-Z0-9_]+\b/, Name::Constant    # IDS constants (all collapse to one colour upstream)
        rule %r/[()\[\].,#]/, Punctuation
        rule %r/./, Text
      end

      state :comment_block do
        rule %r{\*/}, Comment::Multiline, :pop!
        rule %r/[^*]+/, Comment::Multiline
        rule %r/\*/, Comment::Multiline
      end

      state :string do
        rule %r/"/, Str::Double, :pop!
        rule %r/%[^%]+%/, Name::Variable
        rule %r/\b(?:GLOBAL|LOCALS|MYAREA)\b/, Keyword
        rule %r/[^"%]+/, Str::Double
        rule %r/%/, Str::Double
      end

      # Inside IF ... THEN: function calls are triggers.
      state :condition do
        rule %r/\bTHEN\b/, Keyword, :pop!
        rule %r/[A-Za-z_]\w*(?=\()/, Name::Function     # trigger
        mixin :content
      end

      # Inside RESPONSE ... END: function calls are actions.
      state :action do
        rule %r/\bEND\b/, Keyword, :pop!
        rule %r/(\bRESPONSE\b)(\s+)(#\d+)/ do           # further responses in the same block
          groups Keyword, Text::Whitespace, Num::Integer
        end
        rule %r/[A-Za-z_]\w*(?=\()/, Name::Builtin      # action
        mixin :content
      end

      state :root do
        rule %r/\bIF\b/, Keyword, :condition
        rule %r/(\bRESPONSE\b)(\s+)(#\d+)/ do
          groups Keyword, Text::Whitespace, Num::Integer
          push :action
        end
        rule %r/\b(?:THEN|END)\b/, Keyword              # tolerate stray terminators in partial snippets
        # Root-level calls have no IF/RESPONSE context to classify them. Standalone BAF defaults to trigger;
        # when embedded in a WeiDU D tilde region the `embed` option says which context applies (DO -> action).
        rule %r/[A-Za-z_]\w*(?=\()/ do |m|
          # Rouge stores option keys as strings.
          token((@options["embed"].to_s == "action" ? Name::Builtin : Name::Function), m[0])
        end
        mixin :content
      end
    end
  end
end
