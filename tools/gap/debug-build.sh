mkdir build
cd build
cmake -S .. -B . -DCMAKE_BUILD_TYPE=Debug -DCMAKE_INSTALL_PREFIX="$HOME/.local/devilutionx"

make -j "$(nproc)"

# (optional but handy when running from the build tree too)
make devilutionx_copied_assets

# install into ~/.local (puts the binary on ~/.local/bin and data in ~/.local/share)
#make install
