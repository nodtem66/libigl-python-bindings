import os
import re
import sys
import platform
import subprocess

from packaging import version
from setuptools import setup, Extension, find_packages
from setuptools.command.build_ext import build_ext

# Convert distutils Windows platform specifiers to CMake -A arguments
PLAT_TO_CMAKE = {
    "win32": "Win32",
    "win-amd64": "x64",
    "win-arm32": "ARM",
    "win-arm64": "ARM64",
}

class CMakeExtension(Extension):
    def __init__(self, name, sourcedir=''):
        Extension.__init__(self, name, sources=[])
        self.sourcedir = os.path.abspath(sourcedir)


class CMakeBuild(build_ext):
    def run(self):
        try:
            out = subprocess.check_output(['cmake', '--version'])
        except OSError:
            raise RuntimeError(
                "CMake must be installed to build the following extensions: , ".join(e.name for e in self.extensions))

        # self.debug = True

        cmake_version = version.parse(re.search(r'version\s*([\d.]+)', out.decode()).group(1))
        if cmake_version < version.Version('3.2.0'):
            raise RuntimeError("CMake >= 3.2.0 is required")

        for ext in self.extensions:
            self.build_extension(ext)


    def build_extension(self, ext):
        extdir = os.path.join(os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name))),"igl")
        
        cfg = 'Debug' if self.debug else 'Release'

        cmake_args = [
            "-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={}".format(extdir),
            "-DPYTHON_EXECUTABLE={}".format(sys.executable),
            "-DCMAKE_BUILD_TYPE={}".format(cfg),  # not used on MSVC, but no harm
        ]

        build_args = []

        # cmake_args += ['-DDEBUG_TRACE=ON']

        # CMake lets you override the generator - we need to check this.
        # Can be set with Conda-Build, for example.
        cmake_generator = os.environ.get('CMAKE_GENERATOR', '')
        
        if self.compiler.compiler_type != "msvc":
            # Using Ninja-build since it a) is available as a wheel and b)
            # multithreads automatically. MSVC would require all variables be
            # exported for Ninja to pick it up, which is a little tricky to do.
            # Users can override the generator with CMAKE_GENERATOR in CMake
            # 3.15+.
            if not cmake_generator:
                cmake_args += ["-GNinja"]

        else:

            # Single config generators are handled "normally"
            single_config = any(x in cmake_generator for x in {"NMake", "Ninja"})

            # CMake allows an arch-in-generator style for backward compatibility
            contains_arch = any(x in cmake_generator for x in {"ARM", "Win64"})

            # Specify the arch if using MSVC generator, but only if it doesn't
            # contain a backward-compatibility arch spec already in the
            # generator name.
            if not single_config and not contains_arch:
                cmake_args += ["-A", PLAT_TO_CMAKE[self.plat_name]]

            # Multi-config generators have a different way to specify configs
            if not single_config:
                cmake_args += [
                    "-DCMAKE_ARCHIVE_OUTPUT_DIRECTORY_{}={}".format(cfg.upper(), extdir),
                    "-DCMAKE_LIBRARY_OUTPUT_DIRECTORY_{}={}".format(cfg.upper(), extdir),
                    "-DCMAKE_RUNTIME_OUTPUT_DIRECTORY_{}={}".format(cfg.upper(), extdir)
                ]
                build_args += ["--config", cfg]

        # Custom CMAKE ARGS and Compiler
        tmp = os.environ.get("AR", "")
        if "arm64-apple" in tmp:
            tmp = os.environ.get("CMAKE_ARGS", "")
            if tmp:
                cmake_args += tmp.split(" ")

            tmp = os.environ.get("CC", "")
            print("C compiler", tmp)
            if tmp:
                cmake_args += ["-DCMAKE_C_COMPILER={}".format(tmp)]

            tmp = os.environ.get("CXX", "")
            print("CXX compiler", tmp)
            if tmp:
                cmake_args += ["-DCMAKE_CXX_COMPILER={}".format(tmp)]
        else:
            tmp = os.getenv('CC_FOR_BUILD', '')
            if tmp:
                print("Setting c compiler to", tmp)
                cmake_args += ["-DCMAKE_C_COMPILER=" + tmp]

            tmp = os.getenv('CXX_FOR_BUILD', '')
            if tmp:
                print("Setting cxx compiler to", tmp)
                cmake_args += ["-DCMAKE_CXX_COMPILER="+ tmp]

        env = os.environ.copy()
        env['CXXFLAGS'] = '{} -DVERSION_INFO=\\"{}\\"'.format(env.get('CXXFLAGS', ''),self.distribution.get_version())

        # Set CMAKE_BUILD_PARALLEL_LEVEL to control the parallel build level
        # across all generators.
        if "CMAKE_BUILD_PARALLEL_LEVEL" not in os.environ:
            # self.parallel is a Python 3 only way to set parallel jobs by hand
            # using -j in the build_ext call, not supported by pip or PyPA-build.
            if hasattr(self, "parallel") and self.parallel:
                # CMake 3.12+ only.
                build_args += ["-j{}".format(self.parallel)]

        tmp = os.getenv("target_platform", "")
        if tmp:
            print("target platfrom", tmp)
            if "arm" in tmp:
                cmake_args += ["-DCMAKE_OSX_ARCHITECTURES=arm64"]

        # print(cmake_args)
        # tmp = os.getenv('CMAKE_ARGS', '')

        # if tmp:
        #     tmp = tmp.split(" ")
        #     print("tmp", tmp)
        #     cmake_args += tmp

        # cmake_args += ["-DCMAKE_OSX_ARCHITECTURES" , "arm64"]
        # print(cmake_args)

        if not os.path.exists(self.build_temp):
            os.makedirs(self.build_temp)

        subprocess.check_call(['cmake', ext.sourcedir] + cmake_args, cwd=self.build_temp, env=env)

        subprocess.check_call(['cmake', '--build', '.'] + build_args, cwd=self.build_temp)

        print()  # Add an empty line for cleaner output


with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="igl",
    version="2022.2.0",
    author="libigl",
    author_email="",
    description="libigl Python Bindings",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://libigl.github.io/libigl-python-bindings/",
    ext_modules=[CMakeExtension('pyigl')],
    install_requires=[ 'numpy', 'scipy' ],
    cmdclass=dict(build_ext=CMakeBuild),
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License"
    ],
    test_suite="tests"
)
