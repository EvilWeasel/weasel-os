local catppuccin = require("catppuccin")

catppuccin.setup({
  flavour = "mocha",
  transparent_background = false,
  no_italic = false,
  no_bold = false,
  integrations = {
    cmp = true,
    indent_blankline = {
      enabled = true,
    },
    native_lsp = {
      enabled = true,
      underlines = {
        errors = { "underline" },
        hints = { "underline" },
        information = { "underline" },
        warnings = { "underline" },
      },
    },
    nvimtree = true,
    telescope = true,
    treesitter = true,
    which_key = true,
  },
})

vim.cmd.colorscheme("catppuccin-mocha")
