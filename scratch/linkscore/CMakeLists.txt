# Mỗi .cc trong scratch/linkscore/ là một scenario độc lập -> một target riêng.
#
# Vì sao cần file này: nếu để scratch/CMakeLists.txt tự glob thư mục, MỌI .cc
# trong đây bị gộp vào một target và build lỗi "multiple main functions" ngay
# khi thêm link-dataset.cc ở P2.
#
# EXECNAME_PREFIX phải đúng là scratch_linkscore_ : `./ns3 build link-probe` và
# `./ns3 run scratch/linkscore/link-probe` tự dựng tên target theo đường dẫn
# thư mục. Đặt prefix khác thì ninja build được nhưng ./ns3 báo
# "Target to build does not exist".
file(GLOB linkscore_scratches CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/[^.]*.cc)
foreach(scratch_src ${linkscore_scratches})
  get_filename_component(scratch_name ${scratch_src} NAME_WLE)
  build_exec(
    EXECNAME ${scratch_name}
    EXECNAME_PREFIX scratch_linkscore_
    SOURCE_FILES ${scratch_src}
    LIBRARIES_TO_LINK "${ns3-libs}" "${ns3-contrib-libs}"
    EXECUTABLE_DIRECTORY_PATH ${CMAKE_OUTPUT_DIRECTORY}/scratch/linkscore/
  )
endforeach()
