#!/bin/bash

head -c 9 /dev/urandom | uuencode -m - | head -2 | tail -1 |  tr '1IlO0' '$/%&#'
