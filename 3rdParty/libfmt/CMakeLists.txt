include(functions/FetchContent_ExcludeFromAll_backport)

if(NOT WIN32 AND NOT APPLE AND NOT ${CMAKE_SYSTEM_NAME} STREQUAL FreeBSD)
  # Enable POSIX extensions such as `readlink` and `ftruncate`.
  add_definitions(-D_POSIX_C_SOURCE=200809L)
endif()

# Disable fmt/os.h functionality.
# We do not use it and it is not supported on some systems.
set(FMT_OS OFF)

# Mark libfmt's headers as SYSTEM so front-end warnings from fmt (deprecations,
# etc.) don't surface as ours. FORCE into the cache: fmt's own option() runs in a
# scope where a plain set() of the same name may not win (CMP0077), so the cache
# entry is the reliable lever.
set(FMT_SYSTEM_HEADERS ON CACHE BOOL "Expose fmt headers as SYSTEM to silence their warnings" FORCE)

if(DEVILUTIONX_STATIC_LIBFMT)
  set(BUILD_SHARED_LIBS OFF)
else()
  set(BUILD_SHARED_LIBS ON)
endif()
include(FetchContent)
FetchContent_Declare_ExcludeFromAll(libfmt
  URL https://github.com/fmtlib/fmt/archive/02537548f3a9efb5f3b83755acf50c8a16ba58c8.tar.gz
  URL_HASH MD5=6901c6945cd311117d96baaa6d067380
)
FetchContent_MakeAvailable_ExcludeFromAll(libfmt)

# We do not use locale-specific features of libfmt and disabling them reduces the size.
target_compile_definitions(fmt PUBLIC FMT_USE_LOCALE=0)

# Silence GCC's -Wstringop-overflow false positive inside fmt's compile-time string
# escaping (<fmt/base.h> for_each_codepoint / write_escaped_string). It's a known
# GCC 13+ middle-end bug: the warning is emitted after inlining, so marking fmt's
# headers SYSTEM (above) does NOT suppress it — only -Wno does. Scoped to the fmt
# target (INTERFACE → fmt consumers) and to GCC so our own code keeps the warning
# everywhere fmt isn't inlined in. This was ~8 warnings on every incremental build.
if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
  target_compile_options(fmt INTERFACE -Wno-stringop-overflow)
endif()

if(DEVILUTIONX_WINDOWS_NO_WCHAR)
  target_compile_definitions(fmt PUBLIC FMT_USE_WRITE_CONSOLE)
endif()

# Reduces the overall binary size by 8 KiB.
if(TARGET_PLATFORM STREQUAL "rg99")
  target_compile_definitions(fmt PUBLIC FMT_BUILTIN_TYPES=0)
endif()

# https://github.com/fmtlib/fmt/issues/4189
if(NINTENDO_3DS OR NINTENDO_SWITCH OR VITA)
  target_compile_definitions(fmt PUBLIC FMT_USE_FALLBACK_FILE=1)
endif()
