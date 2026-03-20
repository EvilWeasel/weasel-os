local cmp_nvim_lsp = require("cmp_nvim_lsp")
local which_key = require("which-key")

local capabilities = cmp_nvim_lsp.default_capabilities()
local repo_root = vim.env.WEASEL_OS_ROOT
if repo_root == nil or repo_root == "" then
  repo_root = vim.fn.expand("~") .. "/weasel-os"
end

local host_name = vim.env.WEASEL_OS_HOST
if host_name == nil or host_name == "" then
  host_name = "nixy-laptop"
end

vim.diagnostic.config({
  severity_sort = true,
  float = {
    border = "rounded",
    source = "if_many",
  },
  virtual_text = true,
})

local function bufmap(bufnr, lhs, rhs, desc)
  vim.keymap.set("n", lhs, rhs, {
    buffer = bufnr,
    desc = desc,
    silent = true,
  })
end

local function setup(server_name, settings)
  vim.lsp.config(server_name, vim.tbl_deep_extend("force", {
    capabilities = capabilities,
  }, settings or {}))
end

local function enable(server_name)
  vim.lsp.enable(server_name)
end

vim.api.nvim_create_autocmd("LspAttach", {
  callback = function(event)
    local bufnr = event.buf

    which_key.add({
      { "<leader>l", group = "LSP", buffer = bufnr },
    })

    bufmap(bufnr, "gd", vim.lsp.buf.definition, "Go to definition")
    bufmap(bufnr, "gD", vim.lsp.buf.declaration, "Go to declaration")
    bufmap(bufnr, "gi", vim.lsp.buf.implementation, "Go to implementation")
    bufmap(bufnr, "gr", vim.lsp.buf.references, "List references")
    bufmap(bufnr, "K", vim.lsp.buf.hover, "Hover docs")
    bufmap(bufnr, "<leader>la", vim.lsp.buf.code_action, "Code action")
    bufmap(bufnr, "<leader>ld", vim.diagnostic.open_float, "Line diagnostics")
    bufmap(bufnr, "<leader>lf", function()
      vim.lsp.buf.format({ async = true })
    end, "Format buffer")
    bufmap(bufnr, "<leader>lr", vim.lsp.buf.rename, "Rename symbol")
    bufmap(bufnr, "<leader>ls", vim.lsp.buf.signature_help, "Signature help")
    bufmap(bufnr, "[d", vim.diagnostic.goto_prev, "Previous diagnostic")
    bufmap(bufnr, "]d", vim.diagnostic.goto_next, "Next diagnostic")
  end,
})

setup("bashls")
setup("csharp_ls")
setup("dockerls")
setup("gopls")
setup("lua_ls", {
  settings = {
    Lua = {
      diagnostics = {
        globals = { "vim" },
      },
      runtime = {
        version = "LuaJIT",
      },
      workspace = {
        checkThirdParty = false,
      },
    },
  },
})
setup("marksman")
setup("nixd", {
  settings = {
    nixd = {
      formatting = {
        command = { "alejandra" },
      },
      options = {
        nixos = {
          expr = string.format(
            "(builtins.getFlake (toString %q)).nixosConfigurations.%s.options",
            repo_root,
            host_name
          ),
        },
      },
    },
  },
})
setup("pyright")
setup("rust_analyzer", {
  settings = {
    ["rust-analyzer"] = {
      cargo = {
        allFeatures = true,
      },
      checkOnSave = {
        command = "clippy",
      },
    },
  },
})
setup("taplo")
setup("ts_ls", {
  init_options = {
    hostInfo = "neovim",
  },
})
setup("yamlls", {
  settings = {
    yaml = {
      format = {
        enable = true,
      },
      keyOrdering = false,
    },
  },
})

enable("bashls")
enable("csharp_ls")
enable("dockerls")
enable("gopls")
enable("lua_ls")
enable("marksman")
enable("nixd")
enable("pyright")
enable("rust_analyzer")
enable("taplo")
enable("ts_ls")
enable("yamlls")
