// Prints the clang version that compiled this file. It uses libc++, so the link needs libc++ too.
#include <iostream>
#include <string>

int main() {
#ifdef __apple_build_version__
  std::cout << "apple clang\n";
  return 0;
#else
  std::string version = std::to_string(__clang_major__) + " " + std::to_string(__clang_minor__) +
                        " " + std::to_string(__clang_patchlevel__);
  std::cout << version << "\n";
  return 0;
#endif
}
