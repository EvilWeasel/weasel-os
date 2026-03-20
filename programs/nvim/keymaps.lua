local keymap = vim.keymap
local which_key = require("which-key")

which_key.add({
  { "<leader>e", group = "Explorer" },
  { "<leader>f", group = "Find" },
  { "<leader>l", group = "LSP" },
  { "<leader>n", group = "Search" },
  { "<leader>s", group = "Splits" },
  { "<leader>t", group = "Tabs" },
  { "<leader>w", group = "Workspace" },
})

-- use jk to exit insert mode
keymap.set("i", "jk", "<ESC>", { desc = "Exit insert mode with jk" })
-- clear search highlights
keymap.set("n", "<leader>nh", "<cmd>nohlsearch<CR>", { desc = "Clear search highlights" })
-- window management
keymap.set("n", "<leader>sv", "<C-w>v", { desc = "Split vertically" })
keymap.set("n", "<leader>sh", "<C-w>s", { desc = "Split horizontally" })
keymap.set("n", "<leader>se", "<C-w>=", { desc = "Equalize splits" })
keymap.set("n", "<leader>sx", "<cmd>close<CR>", { desc = "Close split" })
-- tabs
keymap.set("n", "<leader>to", "<cmd>tabnew<CR>", { desc = "Open tab" })
keymap.set("n", "<leader>tx", "<cmd>tabclose<CR>", { desc = "Close tab" })
keymap.set("n", "<leader>tn", "<cmd>tabn<CR>", { desc = "Next tab" })
keymap.set("n", "<leader>tp", "<cmd>tabp<CR>", { desc = "Previous tab" })
keymap.set("n", "<leader>tf", "<cmd>tabnew %<CR>", { desc = "Move buffer to tab" })
-- search and files
keymap.set("n", "<leader>fe", "<cmd>NvimTreeToggle<CR>", { desc = "Toggle explorer" })
keymap.set("n", "<leader>ff", "<cmd>Telescope find_files<CR>", { desc = "Find files" })
keymap.set("n", "<leader>fg", "<cmd>Telescope live_grep<CR>", { desc = "Live grep" })
keymap.set("n", "<leader>fb", "<cmd>Telescope buffers<CR>", { desc = "Find buffers" })
keymap.set("n", "<leader>fh", "<cmd>Telescope help_tags<CR>", { desc = "Help tags" })
keymap.set("n", "<leader>ft", "<cmd>TodoTelescope<CR>", { desc = "Find todos" })
-- workspace/session
keymap.set("n", "<leader>wr", "<cmd>AutoSession restore<CR>", { desc = "Restore session" })
keymap.set("n", "<leader>ws", "<cmd>AutoSession save<CR>", { desc = "Save session" })
