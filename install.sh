#!/usr/bin/env bash


jar11_url="https://github.com/buntec/scalavista/releases/download/v0.1.0/scalavista-0.1.0_2.11.jar"
jar12_url="https://github.com/buntec/scalavista/releases/download/v0.1.0/scalavista-0.1.0_2.12.jar"

# download scalavista jars if necessary
wget $jar11_url -nc -P jars
wget $jar12_url -nc -P jars

cur_dir=`pwd`

# create symlink to launcher script
ln -sfv "$cur_dir/scalavista" /usr/local/bin/scalavista

pip3 install neovim --upgrade
pip3 install requests --upgrade
pip3 install crayons --upgrade

# :UpdateRemotePlugins
nvim +UpdateRemotePlugins +qa
