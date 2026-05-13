#!/bin/bash
python -m modelscope.cli.cli login --token "ms-c7571aad-01b6-4fbc-98de-a751e7b18902"
python -m modelscope.cli.cli download --model kernelmind/Sam3 --local_dir ./