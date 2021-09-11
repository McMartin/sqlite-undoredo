# Copyright 2021 Alain Martin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

cmake_minimum_required(VERSION 3.8)

project(sqlite-undoredo)


add_executable(test_sqlite_undoredo
  test_sqlite_undoredo.cpp
  "${CMAKE_CURRENT_LIST_DIR}/../third-party/sqlite-amalgamation-3360000/sqlite3.c"
)

target_compile_features(test_sqlite_undoredo PRIVATE cxx_std_17)

target_include_directories(test_sqlite_undoredo PRIVATE
  "${CMAKE_CURRENT_LIST_DIR}/../third-party/cpp-sqlitelib"
  "${CMAKE_CURRENT_LIST_DIR}/../third-party/doctest-2.4.6"
  "${CMAKE_CURRENT_LIST_DIR}/../third-party/sqlite-amalgamation-3360000"
)

if(CMAKE_HOST_SYSTEM_NAME STREQUAL "Linux")
  target_link_libraries(test_sqlite_undoredo PRIVATE -ldl -pthread)
endif()


enable_testing()

add_test(NAME test_sqlite_undoredo COMMAND test_sqlite_undoredo)
