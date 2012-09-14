#/bin/bash
echo ----------------------------------------------------------------
echo sIBL_GUI XSI Server - Files Gathering
echo ----------------------------------------------------------------

#! Gathering folder cleanup.
rm -rf ./releases/repository/*

#! Change log gathering.
cp ./releases/Changes.html ./releases/repository/

#! Addon gathering.
cd ./Addons/
zip -r ../releases/repository/TCPServer_For_Softimage.zip TCPServer_For_Softimage.xsiaddon