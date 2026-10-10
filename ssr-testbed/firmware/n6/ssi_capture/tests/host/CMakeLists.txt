cmake_minimum_required(VERSION 3.22)
project(ssi_host_tests C)
set(CMAKE_C_STANDARD 11)
enable_testing()

set(APP ${CMAKE_CURRENT_SOURCE_DIR}/../../FSBL/App)
set(TOOLS ${CMAKE_CURRENT_SOURCE_DIR}/../../../tools)
add_compile_options(-Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined)
add_link_options(-fsanitize=address,undefined)
include_directories(${APP}/Inc)

add_executable(test_avx_block test_avx_block.c ${APP}/Src/avx_block.c)
add_executable(test_audio_decode test_audio_decode.c ${APP}/Src/audio_decode.c)
add_executable(test_acq_logic test_acq_logic.c ${APP}/Src/acq_logic.c)
add_executable(test_link_logic test_link_logic.c ${APP}/Src/link_logic.c)

add_test(NAME avx_block COMMAND test_avx_block ${CMAKE_CURRENT_BINARY_DIR}/avx_sample.bin)
add_test(NAME avx_block_py COMMAND python3 -I ${TOOLS}/avx_block.py check
         ${CMAKE_CURRENT_BINARY_DIR}/avx_sample.bin --expect type=4 version=1 seq=7
         t0_us=140000 n=20 flags=2 ts0=140000 ts19=149500 adc0_0=100 adc19_2=3994
         voz0_0=-32768 voz0_1=32767 voz0_2=-1 voz0_3=0 voz0_4=-2 voz19_7=308)
set_tests_properties(avx_block_py PROPERTIES DEPENDS avx_block)
add_test(NAME rpi_spi_check COMMAND python3 -I ${TOOLS}/test_rpi_spi_check.py
         ${CMAKE_CURRENT_BINARY_DIR}/avx_sample.bin)
set_tests_properties(rpi_spi_check PROPERTIES DEPENDS avx_block)
add_test(NAME audio_decode COMMAND test_audio_decode)
add_test(NAME acq_logic COMMAND test_acq_logic)
add_test(NAME link_logic COMMAND test_link_logic)
