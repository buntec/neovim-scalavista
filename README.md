# neovim-scalavista

A Neovim plugin that provides basic IDE-like functionality for the Scala language (2.11 and 2.12):

* Show type under cursor (`:ScalavistaType`).
* Jump to definition (`:ScalavistaGoto` - does not currently work for external dependencies).
* Show Scaladoc (`:ScalavistaDoc`)
* Auto-completion (via omni completion - `i_CTRL-X_CTRL-O`).
* Linting (compiler errors/warnings show up as gutter signs and in the quickfix window - this happens on-the-fly; 
no manual compilation is needed)

scalavista is not as feature-complete as [ENSIME](https://github.com/ensime) but instead aims 
to be minimalistic and lightweight. (In particular, it does not work for Java sources.)

The Neovim plugin is a front-end to the [scalavista](https://github.com/buntec/scalavista) language-server, 
which in turn is a thin wrapper around Scala's presentation compiler.

## Prerequisites

* Neovim with Python3 support.
* The `install.sh` script uses `wget` to download the scalavista back-end jars 
and `pip3` to install the required Python packages.
* sbt and the [sbt-scalavista](https://github.com/buntec/sbt-scalavista) plugin are recommended. 

## Install

Using [vim-plug](https://github.com/junegunn/vim-plug):

```
Plug 'buntec/neovim-scalavista', { 'do': './install.sh' }
```

## Usage

The install script symlinks the `scalavista` python3 script into `/usr/local/bin`. 
Execute it from the root of your project, ideally with a `scalavista.json` present. 
A scalavista server will be launched and Neovim will connect to it upon opening any Scala
source file in a buffer.

For an optimal experience use the [sbt-scalavista](https://github.com/buntec/sbt-scalavista) plugin 
to generate a `scalavista.json` file for your project. This is a simple json file with the following fields:

1. `classpath` (i.e., your dependencies)
1. `scalaBinaryVersion` (2.11 or 2.12)
1. `sources` - a list of your existing Scala source files (don't worry, newly creates files will be picked up on-the-fly)
1. `scalacOptions` - a list of scalac compiler options

You can use scalavista without a `scalavista.json` with the effect that external dependencies are 
not recognized and marked as errors in your code. The exception are manually managed dependencies in `./lib` which are
automatically appended to the classpath. You may want to use the `-r` flag to instruct scalavista to look into all
subdirectories for Scala source files and not just in the current directory (this has no effect in the presence of a
`scalavista.json`). 

Use `--help` to see a list of options.

## Disclaimer

This project is in alpha stage and should be considered unstable. 
