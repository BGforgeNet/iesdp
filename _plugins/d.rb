# frozen_string_literal: true

# Rouge lexer for WeiDU D, the Infinity Engine dialogue source shown in the IESDP scripting docs.
#
# Dialogue directives (BEGIN, CHAIN, INTERJECT, REPLACE*) and flow keywords (IF, THEN, SAY, REPLY, GOTO,
# EXTERN, DO, EXIT) are coloured. Tilde-delimited regions are context-sensitive, mirroring the BGforge-MLS
# weidu-d grammar: `IF ~...~` / `+ ~...~` hold BAF triggers and `DO ~...~` holds BAF actions, so those are
# delegated to the BAF lexer (with the embed flag that selects trigger vs action colouring); every other
# tilde region (SAY/REPLY/JOURNAL display text) is a plain string.
#
# Registered under `d` to match ```d fenced blocks and the .d file extension. This intentionally shadows
# Rouge's built-in D-programming-language lexer, which IESDP never uses; the build is verified to confirm
# this lexer wins the registration.

require 'rouge'

module Rouge
  module Lexers
    class WeiduD < RegexLexer
      title 'D (WeiDU)'
      desc 'WeiDU D - Infinity Engine dialogue source'
      tag 'd'
      filenames '*.d'

      # Structural directives -> builtin colour
      DIRECTIVES = %w[
        ADD_STATE_TRIGGER ADD_TRANS_ACTION ADD_TRANS_TRIGGER ALTER_TRANS APPEND APPEND_EARLY BEGIN CHAIN
        EXTEND_BOTTOM EXTEND_TOP INTERJECT INTERJECT_COPY_TRANS INTERJECT_COPY_TRANS2 INTERJECT_COPY_TRANS3
        INTERJECT_COPY_TRANS4 REPLACE REPLACE_ACTION_TEXT REPLACE_ACTION_TEXT_PROCESS
        REPLACE_ACTION_TEXT_PROCESS_REGEXP REPLACE_ACTION_TEXT_REGEXP REPLACE_SAY REPLACE_STATE_TRIGGER
        REPLACE_TRANS_ACTION REPLACE_TRANS_TRIGGER REPLACE_TRIGGER_TEXT REPLACE_TRIGGER_TEXT_REGEXP
        R_A_T_P_R SET_WEIGHT
      ].sort_by { |w| -w.length }

      # Dialogue flow / control keywords (IF, DO and + are handled separately - they open BAF tilde regions)
      KEYWORDS = %w[
        UNLESS COPY_TRANS COPY_TRANS_LATE APPENDI CHAIN2 SAY FLAGS JOURNAL REPLY SOLVED_JOURNAL
        UNSOLVED_JOURNAL EXIT EXTERN GOTO BRANCH END GLOBAL IF_FILE_EXISTS LOCALS MYAREA OR RESPONSE SAFE
        THEN WEIGHT nonPausing
      ].sort_by { |w| -w.length }

      state :root do
        rule %r{//.*}, Comment::Single
        rule %r{/\*}, Comment::Multiline, :comment
        rule %r/\s+/, Text::Whitespace

        # Code-bearing tilde regions: IF/+ -> BAF triggers, DO -> BAF actions. The keyword, whitespace and
        # opening ~ are coloured here; the region body is delegated to the BAF lexer until the closing ~.
        rule %r/(\bIF\b)(\s+)(~)/ do
          groups Keyword, Text::Whitespace, Str
          push :baf_trigger
        end
        rule %r/(\+)(\s*)(~)/ do
          groups Keyword, Text::Whitespace, Str
          push :baf_trigger
        end
        rule %r/(\bDO\b)(\s+)(~)/ do
          groups Keyword, Text::Whitespace, Str
          push :baf_action
        end

        rule %r/~[^~]*~/, Str                # display-text tilde region (SAY/REPLY/JOURNAL)
        rule %r/"[^"]*"/, Str::Double
        rule %r/%[^%]+%/, Name::Variable      # %variable% substitution
        rule %r/@\d+/, Name::Variable         # tra reference
        rule %r/#\d+/, Num::Integer           # strref
        rule %r/\b0x[0-9a-fA-F]+\b/, Num::Hex
        rule %r/\b\d+\b/, Num::Integer
        rule %r/\b(?:#{DIRECTIVES.join('|')})\b/, Name::Builtin
        rule %r/\b(?:#{KEYWORDS.join('|')})\b/, Keyword
        rule %r/\+/, Keyword
        rule %r/[A-Za-z_]\w*/, Text            # state labels, file names, identifiers
        rule %r/./, Text
      end

      # BAF embedded in a tilde region; the closing ~ returns to dialogue context. The body is handed to the
      # BAF lexer with the embed flag so bare calls colour as triggers or actions to match a real BAF block.
      state :baf_trigger do
        rule %r/~/, Str, :pop!
        rule(/[^~]+/) { |m| delegate Baf.new(embed: :trigger), m[0] }
      end

      state :baf_action do
        rule %r/~/, Str, :pop!
        rule(/[^~]+/) { |m| delegate Baf.new(embed: :action), m[0] }
      end

      state :comment do
        rule %r{\*/}, Comment::Multiline, :pop!
        rule %r/[^*]+/, Comment::Multiline
        rule %r/\*/, Comment::Multiline
      end
    end
  end
end
