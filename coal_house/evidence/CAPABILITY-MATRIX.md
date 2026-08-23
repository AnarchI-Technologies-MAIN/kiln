# Kiln coal-house capability matrix

Generated from validated pack contracts, live runtime probes, and qualification evidence whose contract hash matches the current pack.

| Adapter | Languages | Build systems | Test runners | Venv adapter | Implemented | Runtime available | Production proven | Metal earned |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| c-cmake | c | cmake | ctest | cmake-sandbox | yes | no | no | no |
| cpp-cmake | cpp | cmake | ctest | cmake-sandbox | yes | no | no | no |
| dart | dart | dart-pub | dart-script | dart-pub | yes | no | no | no |
| dotnet | csharp | msbuild | dotnet-test | dotnet-nuget | yes | no | no | no |
| elixir-mix | elixir | mix | exunit | elixir-mix | yes | no | no | no |
| go | go | go-modules | go-test | go-modules | yes | no | no | no |
| haskell-cabal | haskell | cabal | cabal-test | haskell-cabal | yes | no | no | no |
| java-maven | java | maven | junit-jupiter, maven-surefire | java-maven | yes | no | no | no |
| kotlin-gradle | kotlin | gradle | junit-jupiter | kotlin-gradle | yes | no | no | no |
| lua | lua | lua-module-path | lua-script | lua-path | yes | no | no | no |
| php-composer | php | composer | php-script | php-composer | yes | no | no | no |
| python-unittest | python | python-compileall | python-unittest | python-runtime | yes | yes | yes | yes |
| r | r | r-source | rscript | r-library | yes | no | no | no |
| ruby-bundler | ruby | bundler | minitest | ruby-bundler | yes | no | no | no |
| rust-cargo | rust | cargo | cargo-test | rust-cargo | yes | yes | yes | yes |
| swift-swiftpm | swift | swift-package-manager | xctest | swift-swiftpm | yes | no | no | no |
| zig | zig | zig-build | zig-test | zig-cache | yes | no | no | no |

Unavailable runtimes are implemented contracts and fixtures only; they are not passing qualifications.
