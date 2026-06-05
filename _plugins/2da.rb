# frozen_string_literal: true

# Rouge lexer for Infinity Engine 2DA tables.
#
# A 2DA cell is a bare word; nothing in the text says whether a column holds a resref, a probability or a
# row label - that is schema knowledge the file does not carry, so semantic colouring is impossible here.
# So the body is coloured as a "rainbow": each whitespace-delimited column gets a colour by position,
# cycling through six slots (mod 6), matching the BGforge-MLS 2DA semantic-token colours.
#
# The two fixed lines are not positional, so they are coloured statically, matching the BGforge-MLS
# infinity-2da grammar: the "2DA V1.0" signature (keyword + version constant) and the default-value line.

require 'rouge'

module Rouge
  module Lexers
    class Infinity2DA < RegexLexer
      title '2DA'
      desc 'Infinity Engine 2DA table (static signature, rainbow columns)'
      tag '2da'
      filenames '*.2da'

      # Custom per-column tokens; their colours (BGforge Monokai palette) are set in _syntax-highlighting.scss.
      RAINBOW = (0..5).map { |i| Token::Tokens.token("TwoDAC#{i}", "twoda-c#{i}") }.freeze

      start { @col = 0; @line = 0 }

      state :root do
        # signature line, coloured statically: "2DA V" keyword, version constant
        rule %r/\A(2DA\s+V)(\S+)/ do
          groups Keyword, Name::Constant
        end

        rule %r/\n/ do |m|
          @col = 0
          @line += 1
          token Text::Whitespace, m[0]
        end
        rule %r/[ \t]+/, Text::Whitespace
        rule %r/\S+/ do |m|
          if @line == 1
            token Name::Constant, m[0]            # default-value line - static, part of the header block
          else
            # the column-header row (3rd line) has no cell for the row-label column, so shift it one to the
            # right to line its colours up with the data columns it labels
            offset = (@line == 2 ? 1 : 0)
            token RAINBOW[(@col + offset) % RAINBOW.length], m[0]
            @col += 1
          end
        end
      end
    end
  end
end
