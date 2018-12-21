# neovim-scalavista

A Neovim plugin that provides basic IDE-like functionality for the Scala language (2.11 and 2.12):

* Show type under cursor (:ScalavistaType)
* Auto-completion (via omni completion)
* Jump to definition (:ScalavistaGoto) - (does not currently work for external dependencies)
* Linting (gutter signs and quickfix window)

scalavista is not as feature-complete as ENSIME https://github.com/ensime but instead aims to be minimalistic and lightweight. (In particular, it does not work for Java sources.)

This Neovim plugin is a front-end to the scalavista language-server https://github.com/buntec/scalavista, which in turn is a thin wrapper around Scala's presentation compiler.

## Prerequisites

* Neovim with Python3 support.
* The `install.sh` script uses `wget` to download the scalavista back-end jars 
and `pip3` to install the required Python packages.
* sbt and sbt-scalavista plugin are highly recommended. 

## Install

Using [vim-plug](https://github.com/junegunn/vim-plug):

```
Plug 'buntec/neovim-scalavista', { 'do': './install.sh' }
```

For an optimal experience use the sbt-scalavista plugin https://github.com/buntec/sbt-scalavista 
to generate a `scalavista.json` file for your project. This is a simple json file with three fields:

1. `classpath` (i.e., your dependencies)
1. `scalaBinaryVersion` (2.11 or 2.12)
1. `sources` - a list of your existing Scala source files (don't worry, newly creates files will be picked up on-the-fly)

You can use scalavista without a `scalavista.json` but then any external dependencies are 
not recognized and marked as errors in your code. (This may be perfectly fine if you want to 
write a small script or self-contained application.) The binary version defaults to 2.12.

## Usage

The install script symlinks a python3 script `scalavista` into `/usr/local/bin`. 
Execute it from the root of your project, ideally with a `scalavista.json` present. 
A scalavista server will be launched and Neovim will connect to it when opening any Scala
source file. Enjoy!

## Disclaimer

This project is in alpha stage and should be considered unstable. 
