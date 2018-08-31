#!/bin/sh

version=$(python3.7 -V 2>&1 | grep -o '^Python 3.7')
if [[ -z "$version" ]]
then
    echo "Yon need python 3.7 or greater to run this script"
    exit 37
fi

pip3 install -r ./requirements.txt

chmod +x ./timer.py
cp ./timer.py ~/timer.py

if [ ! -f ~/config.ini ]; then
    cp ./config.ini ~/config.ini
    echo 'Config created at ~/config.ini. You need to edit it.'
fi

exit 0