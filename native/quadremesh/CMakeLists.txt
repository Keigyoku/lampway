# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# lampway-quadremesh: a Qt-free command line around the MIT-licensed AutoRemesher core (https://github.com/huxingyi/autoremesher).
# The AutoRemesher sources are NOT in this repository: point AR_SOURCE at a checkout (build.sh fetches the pinned commit).
cmake_minimum_required(VERSION 3.16)
project(lampway_quadremesh CXX)

set(AR_SOURCE "" CACHE PATH "a checkout of huxingyi/autoremesher")
if(NOT AR_SOURCE OR NOT EXISTS "${AR_SOURCE}/src/AutoRemesher/autoremesher.cpp")
  message(FATAL_ERROR "set -DAR_SOURCE=<autoremesher checkout> (see build.sh)")
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()
set(CMAKE_CXX_FLAGS_RELEASE "-O2 -DNDEBUG")
# the bundled TBB (2020-era headers) and the core predate GCC 13's stricter name-lookup diagnostic
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fpermissive -Wno-changes-meaning -w")

# the bundled TBB (static): the core uses tbb::parallel_for and friends
set(TBB_BUILD_SHARED OFF CACHE BOOL "" FORCE)
set(TBB_BUILD_STATIC ON CACHE BOOL "" FORCE)
set(TBB_BUILD_TBBMALLOC OFF CACHE BOOL "" FORCE)
set(TBB_BUILD_TBBMALLOC_PROXY OFF CACHE BOOL "" FORCE)
set(TBB_BUILD_TESTS OFF CACHE BOOL "" FORCE)
add_subdirectory(${AR_SOURCE}/thirdparty/tbb ${CMAKE_BINARY_DIR}/tbb EXCLUDE_FROM_ALL)

file(GLOB CORE_SRC "${AR_SOURCE}/src/AutoRemesher/*.cpp")
file(GLOB ISO_SRC "${AR_SOURCE}/thirdparty/isotropicremesher/*.cpp")
file(GLOB MESHOPT_SRC "${AR_SOURCE}/thirdparty/meshoptimizer/src/*.cpp")

add_executable(lampway-quadremesh main.cpp ${CORE_SRC} ${ISO_SRC} ${MESHOPT_SRC})
target_include_directories(lampway-quadremesh PRIVATE
  ${AR_SOURCE}/include ${AR_SOURCE}/src ${AR_SOURCE}/thirdparty/eigen ${AR_SOURCE}/thirdparty/isotropicremesher
  ${AR_SOURCE}/thirdparty/meshoptimizer/src ${AR_SOURCE}/thirdparty/tbb/include)
target_link_libraries(lampway-quadremesh PRIVATE tbb_static pthread)
