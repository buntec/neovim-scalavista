# neovim-scalavista

Provides basic IDE-like functionality for the Scala language in Neovim. 

* Show type under cursor (:ScalavistaType)
* Auto-completion (via omni completion)
* Jump to definition (:ScalavistaGoto) - (works only within project, not dependencies)
* Linting

scalavista is not as feature-complete as ENSIME but instead aims to be simple and lightweight. 

It requires sbt and the sbt-scalavista plugin https://github.com/buntec/sbt-scalavista.

The Neovim plugin is a simple front-end to the scalavista language-server https://github.com/buntec/scalavista, which in turn is a wrapper around Scala's presentation compiler.

To install using [vim-plug](https://github.com/junegunn/vim-plug):

```
Plug 'buntec/neovim-scalavista', { 'do': './install.sh' }

```

This project is in early alpha stage and should be considered unstable. 
