# neovim-scalavista

![](demo.gif)

A Neovim plugin that provides IDE-like functionality for the Scala language (2.11--2.13):

* Show type under cursor (`:ScalavistaType`);
* Jump to definition (`:ScalavistaGoto` - does not currently work for external dependencies);
* Show Scaladoc (`:ScalavistaDoc`);
* Auto-completion (via Omni completion);
* Linting (compiler errors and warnings show up as you type).


The plugin is a front-end to the [scalavista-server](https://github.com/buntec/scalavista-server)
language server, which in turn is a thin wrapper around Scala's presentation compiler.


## Prerequisites

* Neovim with Python3 support and the `pynvim` package installed (`pip3 install pynvim`);
* Java (version >= 8): make sure the `java` executable is on your `PATH`;
* sbt and the [sbt-scalavista](https://github.com/buntec/sbt-scalavista) plugin are 
  recommended for larger projects and those with external dependencies.


## Install

Using [vim-plug](https://github.com/junegunn/vim-plug):

```
Plug 'buntec/neovim-scalavista', { 'do': [':UpdateRemotePlugins', :ScalavistaDownloadServerJars'] }
```

The `:ScalavistaDownloadServerJars` command is optional (but convenient because it guarantees that you
always use the latest version of the language server) and can also be executed manually.


## Usage

See `:help neovim-scalavista`.
