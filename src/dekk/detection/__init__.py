"""Detection and inspection modules."""

from .build import BuildSystem, BuildSystemDetector, BuildSystemInfo, BuildTarget
from .cache import BuildCacheDetector, BuildCacheInfo, CacheKind
from .ci import CIBuildAdvisor, CIBuildHints, CIDetector, CIInfo, CIProvider
from .compiler import CompilerDetector, CompilerFamily, CompilerInfo, ToolchainInfo
from .conda import COMMON_INSTALL_PATHS, CondaDetector, CondaEnvironment, CondaValidation
from .deps import DependencyChecker, DependencyResult, DependencySpec, ToolChecker
from .detect import PlatformDetector, PlatformInfo
from .libpath import LibraryPathInfo, LibraryPathResolver
from .lockfile import LockfileInfo, LockfileKind, LockfileParser, LockedDependency
from .scaffold import (
    FileTemplate,
    ProjectFramework,
    ProjectLanguage,
    ProjectType,
    ProjectTypeDetector,
    SetupScript,
    SetupScriptBuilder,
    SetupStep,
    TemplateRegistry,
    TemplateSet,
)
from .version_managers import ManagedVersion, VersionManagerDetector, VersionManagerInfo
from .workspace import SubProject, WorkspaceDetector, WorkspaceInfo, WorkspaceKind

__all__ = [
    "BuildCacheDetector",
    "BuildCacheInfo",
    "BuildSystem",
    "BuildSystemDetector",
    "BuildSystemInfo",
    "BuildTarget",
    "COMMON_INSTALL_PATHS",
    "CIBuildAdvisor",
    "CIBuildHints",
    "CIDetector",
    "CIInfo",
    "CIProvider",
    "CacheKind",
    "CompilerDetector",
    "CompilerFamily",
    "CompilerInfo",
    "CondaDetector",
    "CondaEnvironment",
    "CondaValidation",
    "DependencyChecker",
    "DependencyResult",
    "DependencySpec",
    "FileTemplate",
    "LibraryPathInfo",
    "LibraryPathResolver",
    "LockfileInfo",
    "LockfileKind",
    "LockfileParser",
    "LockedDependency",
    "ManagedVersion",
    "PlatformDetector",
    "PlatformInfo",
    "ProjectFramework",
    "ProjectLanguage",
    "ProjectType",
    "ProjectTypeDetector",
    "SetupScript",
    "SetupScriptBuilder",
    "SetupStep",
    "SubProject",
    "TemplateRegistry",
    "TemplateSet",
    "ToolChecker",
    "ToolchainInfo",
    "VersionManagerDetector",
    "VersionManagerInfo",
    "WorkspaceDetector",
    "WorkspaceInfo",
    "WorkspaceKind",
]
