#!/usr/bin/env python

print('I exist to fail...')

try:
    assert 2 == 1, 'I had to faild'
except AssertionError as err:
    print('Assertion error')
