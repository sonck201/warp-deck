#!/usr/bin/env bash
YARN_INSTALLED="$(which yarn)"
DOCKER_INSTALLED="$(which docker)"
CLI_INSTALLED="$(pwd)/cli/decky"

# echo "$YARN_INSTALLED"
# echo "$DOCKER_INSTALLED"
# echo "$CLI_INSTALLED"

echo "If you are using alpine linux, do not expect any support."
if [[ "$YARN_INSTALLED" =~ "which" ]]; then
    echo "yarn not found. This repo pins yarn@4.18.0 via the packageManager field,"
    echo "which Corepack reads automatically. Enable it once with: corepack enable"
    echo "(Corepack ships with Node.js 16.10+; you may need sudo.)"
fi

if [[ "$DOCKER_INSTALLED" =~ "which" ]]; then
    echo "Docker is not currently installed, in order build plugins with a backend you will need to have Docker installed. Please install Docker via the preferred method for your distribution."
fi

if ! test -f "$CLI_INSTALLED"; then
    echo "The Decky CLI tool (binary file is just called "decky") is used to build your plugin as a zip file which you can then install on your Steam Deck to perform testing. We highly recommend you install it. Hitting enter now will run the script to install Decky CLI and extract it to a folder called cli in the current plugin directory. You can also type 'no' and hit enter to skip this but keep in mind you will not have a usable plugin without building it."
    read run_cli_script
    if [[ "$run_cli_script" =~ "n" ]]; then
        echo "You have chosen to not install the Decky CLI tool to build your plugins. Please install this tool to build and test your plugin before submitting it to the Plugin Database."
    else

        SYSTEM_ARCH="$(uname -a)"

        mkdir "$(pwd)"/cli
        if [[ "$SYSTEM_ARCH" =~ "x86_64" ]]; then

            if [[ "$SYSTEM_ARCH" =~ "Linux" ]]; then
                curl -L -o "$(pwd)"/cli/decky "https://github.com/SteamDeckHomebrew/cli/releases/latest/download/decky-linux-x86_64"
            fi
            
            if [[ "$SYSTEM_ARCH" =~ "Darwin" ]]; then
                curl -L -o "$(pwd)"/cli/decky "https://github.com/SteamDeckHomebrew/cli/releases/latest/download/decky-macOS-x86_64"
            fi

        elif [[ "$SYSTEM_ARCH" =~ "arm64" || "$SYSTEM_ARCH" =~ "aarch64" ]]; then
            if [[ "$SYSTEM_ARCH" =~ "Linux" ]]; then
                curl -L -o "$(pwd)"/cli/decky "https://github.com/SteamDeckHomebrew/cli/releases/latest/download/decky-linux-aarch64"
            fi
            
            if [[ "$SYSTEM_ARCH" =~ "Darwin" ]]; then
                curl -L -o "$(pwd)"/cli/decky "https://github.com/SteamDeckHomebrew/cli/releases/latest/download/decky-macOS-aarch64"
            fi

        else
            echo "System Arch not found! The only supported systems are Linux x86_64/ARM64 and Apple x86_64/ARM64, not $SYSTEM_ARCH"
        fi
        
        chmod +x "$(pwd)"/cli/decky
        echo "Decky CLI tool is now installed and you can build plugins into easy zip files using the "Build Zip" Task in vscodium."
    fi
fi
