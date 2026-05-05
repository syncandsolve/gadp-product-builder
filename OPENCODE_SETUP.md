# GADP + OpenCode Configuration Guide

This guide explains how to configure OpenCode to work with the GADP (Governance-Aware Development Protocol) system, including model routing, agent configuration, and compatibility with different agentic harnesses.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Configuration Structure](#configuration-structure)
- [Model Selection](#model-selection)
- [Model Selection Principles](#model-selection-principles)
- [Agent Configuration](#agent-configuration)
- [Permissions](#permissions)
- [Agent Write Permissions](#agent-write-permissions)
- [Agentic Harness Compatibility](#agentic-harness-compatibility)
- [Troubleshooting](#troubleshooting)
- [Examples](#examples)

## Overview

GADP uses a Governor pattern where a primary agent (Governor) orchestrates specialized sub-agents (Builder, Auditor, Planner) for different development tasks. OpenCode's agent routing system enables this by:

1. **Static Model Assignment**: Each sub-agent uses a specific optimized model
2. **Process Isolation**: Task tool dispatch creates clean boundaries between agents
3. **Permission Control**: Each agent has appropriate tool access
4. **Hidden Agents**: Sub-agents don't appear in UI agent switching

## Quick Start

### 1. Create `opencode.json`

Create this file in your project root:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "agent": {
    "gadp-builder": {
      "description": "Implements GADP contracts, runs tests, handles auto-retry",
      "mode": "subagent",
      "model": "nvidia/qwen/qwen3-coder-480b-a35b-instruct",
      "hidden": true,
      "prompt": "{file:./gadp/agents/builder.md}",
      "permission": {
        "read": "allow",
        "edit": "allow",
        "bash": "allow",
        "glob": "allow",
        "grep": "allow",
        "list": "allow",
        "task": "deny",
        "webfetch": "allow"
      }
    },
    "gadp-auditor": {
      "description": "Runs invariant checks, sprint gates, regression detection",
      "mode": "subagent",
      "model": "nvidia/z-ai/glm4.7",
      "hidden": true,
      "prompt": "{file:./gadp/agents/auditor.md}",
      "permission": {
        "read": "allow",
        "edit": "deny",
        "bash": "allow",
        "glob": "allow",
        "grep": "allow",
        "list": "allow",
        "task": "deny",
        "webfetch": "allow"
      }
    },
    "gadp-planner": {
      "description": "Handles new features, architecture changes, /approve-decisions flows",
      "mode": "subagent",
      "model": "nvidia/deepseek-ai/deepseek-v4-flash",
      "hidden": true,
      "prompt": "{file:./gadp/agents/planner.md}",
      "permission": {
        "read": "allow",
        "edit": "deny",
        "bash": "allow",
        "glob": "allow",
        "grep": "allow",
        "list": "allow",
        "task": "deny",
        "webfetch": "allow"
      },
      "additional": {
        "reasoningEffort": "high"
      }
    }
  },
  "provider": {
    "nvidia": {
      "options": {
        "baseURL": "https://integrate.api.nvidia.com/v1",
        "apiKey": "YOUR_NVIDIA_API_KEY_HERE"
      }
    }
  }
}
```

### 2. Configure Your Provider

Replace `YOUR_NVIDIA_API_KEY_HERE` with your actual API key, or configure your preferred provider.

### 3. Start OpenCode

```bash
opencode
```

The Governor will automatically use the configured models when dispatching sub-agents.

## Configuration Structure

### Root Level

```json
{
  "$schema": "https://opencode.ai/config.json",
  "agent": { ... },
  "provider": { ... }
}
```

### Agent Configuration

Each agent requires these fields:

```json
{
  "description": "Human-readable description",
  "mode": "subagent",
  "model": "provider/organization/model-name",
  "hidden": true,
  "prompt": "{file:./path/to/agent.md}",
  "permission": { ... },
  "additional": { ... }
}
```

### Provider Configuration

```json
{
  "provider": {
    "provider-id": {
      "options": {
        "baseURL": "https://api.example.com/v1",
        "apiKey": "your-api-key"
      }
    }
  }
}
```

## Model Selection

### Finding Available Models

**Option 1: Use models.dev API**
```bash
curl https://models.dev/api.json | jq '.nvidia.models | keys'
```

**Option 2: Use OpenCode built-in command**
```bash
opencode models
```

### Model Format

OpenCode uses the format: `provider/organization/model-name`

Examples:
- `nvidia/qwen/qwen3-coder-480b-a35b-instruct`
- `anthropic/claude-sonnet-4-5`
- `openai/gpt-5`

### Model Selection Principles

Governance agents (Auditor and Planner) make decisions with wider blast radius than the Builder. A Builder mistake surfaces in the next test run and is correctable in the same session. An Auditor that misses an invariant violation produces false confidence in a governance gate — bad code ships. A Planner that produces incorrect impact analysis for an architecture change corrupts `decisions.yaml` and requires Flow 2 rollback.

**Rule: Auditor and Planner must always use a full-capability model. Never a lite, flash, or mini variant.**

- `deepseek-v4-flash` → ❌ not for Auditor or Planner. Use `deepseek-v3` or equivalent.
- `glm4.7` → ❌ not for Auditor. Use `glm5` or a full-class reasoning model.
- `qwen3-next-80b-a3b-thinking` → ✅ acceptable for Planner (thinking variant, full class).
- `claude-sonnet-4-5` → ✅ acceptable for both.

**Builder** implements one contract at a time and can recover from a mistake in the next retry. A coding-specialised model at any capability tier is appropriate.

Cost reduction via smaller models is legitimate for the Builder. It is not legitimate for the Auditor or Planner. If cost is a hard constraint on governance agents, document the tradeoff explicitly — do not make it silently.

### Recommended Models by Task

| Task | Recommended Models | Characteristics |
|------|-------------------|-----------------|
| **Code Implementation** | Qwen Coder, Codestral, DeepSeek Coder | Strong code generation, fast |
| **Analysis & Auditing** | GLM-4, Claude Sonnet, GPT-4 | Precise, consistent, thorough |
| **Planning & Architecture** | Kimi K2 Thinking, DeepSeek V4, Qwen Thinking | Deep reasoning, creative |
| **Fast Operations** | Llama 3.3 70B, Mistral Small | Speed-optimized, cost-effective |

### Model Variants

Some models support variants for different use cases:

```json
"additional": {
  "reasoningEffort": "high"  // For reasoning models
}
```

Common variants:
- `reasoningEffort`: `"low"`, `"medium"`, `"high"`
- `temperature`: `0.0` - `1.0` (lower = more deterministic)
- `maxTokens`: Maximum response length
- `topP`: `0.0` - `1.0` (response diversity)

## Agent Configuration

### GADP Builder

**Purpose**: Implements contracts, runs tests, handles auto-retry

**Requirements**:
- Full file access (read + write)
- Bash command execution
- Test running capabilities
- Code generation focus

**Configuration**:
```json
{
  "gadp-builder": {
    "description": "Implements GADP contracts, runs tests, handles auto-retry",
    "mode": "subagent",
    "model": "nvidia/qwen/qwen3-coder-480b-a35b-instruct",
    "hidden": true,
    "prompt": "{file:./gadp/agents/builder.md}",
    "permission": {
      "read": "allow",
      "edit": "allow",
      "bash": "allow",
      "glob": "allow",
      "grep": "allow",
      "list": "allow",
      "task": "deny",
      "webfetch": "allow"
    }
  }
}
```

### GADP Auditor

**Purpose**: Runs invariant checks, sprint gates, regression detection

**Requirements**:
- Read-only file access
- Bash command execution (for checks)
- Analysis and validation focus
- No file modifications

**Configuration**:
```json
{
  "gadp-auditor": {
    "description": "Runs invariant checks, sprint gates, regression detection",
    "mode": "subagent",
    "model": "nvidia/z-ai/glm4.7",
    "hidden": true,
    "prompt": "{file:./gadp/agents/auditor.md}",
    "permission": {
      "read": "allow",
      "edit": "deny",
      "bash": "allow",
      "glob": "allow",
      "grep": "allow",
      "list": "allow",
      "task": "deny",
      "webfetch": "allow"
    }
  }
}
```

### GADP Planner

**Purpose**: Handles new features, architecture changes, /approve-decisions flows

**Requirements**:
- Read-only file access
- Deep reasoning capabilities
- Architecture planning focus
- No file modifications

**Configuration**:
```json
{
  "gadp-planner": {
    "description": "Handles new features, architecture changes, /approve-decisions flows",
    "mode": "subagent",
    "model": "nvidia/deepseek-ai/deepseek-v4-flash",
    "hidden": true,
    "prompt": "{file:./gadp/agents/planner.md}",
    "permission": {
      "read": "allow",
      "edit": "deny",
      "bash": "allow",
      "glob": "allow",
      "grep": "allow",
      "list": "allow",
      "task": "deny",
      "webfetch": "allow"
    },
    "additional": {
      "reasoningEffort": "high"
    }
  }
}
```

## Permissions

### Permission Levels

- `"allow"`: Tool can be used without approval
- `"ask"`: User must approve each use
- `"deny"`: Tool is completely disabled

### Permission Keys

| Key | Tools Controlled | Typical Use |
|-----|-----------------|-------------|
| `read` | File reading | All agents need this |
| `edit` | File modifications | Builder only |
| `bash` | Shell commands | All agents need this |
| `glob` | File pattern matching | All agents need this |
| `grep` | Content search | All agents need this |
| `list` | Directory listing | All agents need this |
| `task` | Subagent dispatch | Subagents should deny this |
| `webfetch` | Web content fetching | Optional for research |

### Permission Patterns

**Full Access (Builder)**:
```json
"permission": {
  "read": "allow",
  "edit": "allow",
  "bash": "allow",
  "glob": "allow",
  "grep": "allow",
  "list": "allow",
  "task": "deny",
  "webfetch": "allow"
}
```

**Read-Only (Auditor/Planner)**:
```json
"permission": {
  "read": "allow",
  "edit": "deny",
  "bash": "allow",
  "glob": "allow",
  "grep": "allow",
  "list": "allow",
  "task": "deny",
  "webfetch": "allow"
}
```

**Restricted Bash Commands**:
```json
"permission": {
  "bash": {
    "*": "ask",
    "npm test": "allow",
    "npm run lint": "allow"
  }
}
```

## Agent Write Permissions

The Auditor and Planner have `"edit": "deny"` in the OpenCode configuration. This is intentional and correct — **but only in OpenCode**. Understanding why matters before adapting GADP to any other harness.

### Why Auditor and Planner have `edit: deny` in OpenCode

The Planner is architecturally a write-heavy agent. It modifies `decisions.yaml`, `invariants.yaml`, contracts, and `openapi.yaml`. The Auditor writes to `audit-log.yaml` and produces `resume_patch` updates. Neither is read-only.

In OpenCode, `"edit": "deny"` does not prevent these writes — it routes them through mutation scripts via `bash`. The Planner calls `python3 gadp/scripts/gadp_update_contract.py` through bash rather than writing YAML directly via the edit tool. `"bash": "allow"` is what enables this. The result is equivalent: YAML files are modified, but only through the validated mutation script path.

This pattern enforces the contract: mutations go through scripts, not direct file writes. It is a mechanical reinforcement of the authority model.

### Claude Code — `edit: deny` does NOT apply

Claude Code does not read `opencode.json`. There is no equivalent permission configuration. When the Governor dispatches the Planner as a sub-agent in Claude Code:

- The Planner uses the **edit tool directly** to write `decisions.yaml`, `invariants.yaml`, and contract updates.
- There is no `edit: deny` in effect. The authority model (Planner only writes these files) is enforced by the Planner's instructions in `planner.md`, not by tool permissions.
- The Planner must still call mutation scripts for GADP YAML (contracts, audit log, intent store) — this is an instruction-enforced rule, not a permission-enforced one.

> ⚠️ **Warning:** If you copy the `"edit": "deny"` permission pattern from `opencode.json` into any Claude Code equivalent configuration, the Planner will fail on every `/approve-decisions` flow. In Claude Code, the Planner's write authority is instruction-enforced. Do not add `edit: deny` for the Planner or Auditor in Claude Code.

### Summary by harness

| Harness | Planner write path | Enforced by |
|---|---|---|
| OpenCode | Mutation scripts via `bash` (`edit: deny` prevents direct writes) | Tool permission + script validation |
| Claude Code | Edit tool directly for governance files; mutation scripts for GADP YAML | Instructions in `planner.md` |
| Other tools | Edit tool directly (same as Claude Code) | Instructions in `planner.md` |

## Agentic Harness Compatibility

### OpenCode (Native)

**Status**: ✅ Full Support

OpenCode has native support for the agent routing system described in this guide. All features work as documented:

- Static model assignment per agent
- Hidden agents from UI
- Custom permissions
- Task tool dispatch
- Model variants

**Configuration**: Use the exact configuration shown in this guide.

### Claude Code

**Status**: ✅ Supported with Task Tool

Claude Code supports the Task tool natively, which GADP uses for sub-agent dispatch. The configuration works identically:

```json
{
  "agent": {
    "gadp-builder": {
      "mode": "subagent",
      "model": "anthropic/claude-sonnet-4-5",
      "hidden": true,
      "prompt": "{file:./gadp/agents/builder.md}",
      "permission": { ... }
    }
  }
}
```

**Key Differences**:
- Uses Anthropic models by default
- Task tool creates subprocess isolation
- Same permission system **with one critical exception** — see Agent Write Permissions section
- `"edit": "deny"` for Auditor/Planner **does not apply in Claude Code**. The Planner uses the edit tool directly for governance files. Do not add `edit: deny` for governance agents in Claude Code — it will break every `/approve-decisions` flow.

### Cursor

**Status**: ✅ Supported

Cursor has built-in support for OpenCode-style agent configuration. Use the same `opencode.json` format:

```json
{
  "agent": {
    "gadp-builder": {
      "mode": "subagent",
      "model": "anthropic/claude-sonnet-4-5",
      "hidden": true,
      "prompt": "{file:./gadp/agents/builder.md}",
      "permission": { ... }
    }
  }
}
```

**Key Differences**:
- May use different default models
- UI integration varies
- Core agent routing works identically

### Windsurf

**Status**: ✅ Supported

Windsurf supports OpenCode configuration files. Place `opencode.json` in your project root:

```json
{
  "agent": {
    "gadp-builder": {
      "mode": "subagent",
      "model": "anthropic/claude-sonnet-4-5",
      "hidden": true,
      "prompt": "{file:./gadp/agents/builder.md}",
      "permission": { ... }
    }
  }
}
```

**Key Differences**:
- Uses same configuration format
- Model availability may differ
- Agent switching UI varies

### Zed

**Status**: ⚠️ Partial Support

Zed has limited support for OpenCode-style agent configuration. You may need to:

1. Use Zed's native agent system
2. Configure models through Zed settings
3. Adapt the GADP protocol for Zed's capabilities

**Workaround**: Use OpenCode TUI alongside Zed for GADP workflows.

### VS Code Extensions

**Status**: ⚠️ Variable Support

Support depends on the specific VS Code extension:

**Continue.dev**:
```json
{
  "agent": {
    "gadp-builder": {
      "mode": "subagent",
      "model": "anthropic/claude-sonnet-4-5",
      "hidden": true,
      "prompt": "{file:./gadp/agents/builder.md}",
      "permission": { ... }
    }
  }
}
```

**Cline**:
- May require different configuration format
- Check extension documentation for agent support

**Roo Code**:
- Limited agent configuration support
- May need protocol adaptation

### Generic Agentic Tools

For tools that don't support OpenCode-style configuration:

**Fallback Approach**:
1. Use the file-based dispatch fallback in GADP
2. Configure models through the tool's native settings
3. Manually invoke agents as needed

**Example Fallback**:
```bash
# GADP will write dispatch prompts to ./tmp/dispatch-[agent]-[timestamp].md
# You can manually start new sessions with these files
```

## Troubleshooting

### Common Issues

#### 1. "Provider model not found" Error

**Cause**: Incorrect model ID format or model doesn't exist

**Solution**:
```bash
# Check available models
curl https://models.dev/api.json | jq '.nvidia.models | keys'

# Verify format: provider/organization/model-name
# Example: nvidia/qwen/qwen3-coder-480b-a35b-instruct
```

#### 2. "API key invalid" Error

**Cause**: Missing or incorrect API key

**Solution**:
```json
{
  "provider": {
    "nvidia": {
      "options": {
        "apiKey": "your-actual-api-key"
      }
    }
  }
}
```

#### 3. Agent Not Dispatching

**Cause**: Task tool not supported or configuration error

**Solution**:
- Verify `opencode.json` syntax is valid
- Check that agent `mode` is set to `"subagent"`
- Ensure `hidden: true` for internal agents
- Review harness compatibility section

#### 4. Permission Denied Errors

**Cause**: Too restrictive permissions

**Solution**:
```json
"permission": {
  "bash": "allow",  // Change from "ask" or "deny"
  "edit": "allow"   // For Builder agent
}
```

#### 5. Model Not Using Variant

**Cause**: Incorrect `additional` field syntax

**Solution**:
```json
"additional": {
  "reasoningEffort": "high"  // Correct
}
```

Not:
```json
"additional": {
  "reasoning_effort": "high"  // Wrong - use camelCase
}
```

### Debug Mode

Enable detailed logging:

```bash
OPENCODE_DEBUG=1 opencode
```

Check configuration:

```bash
opencode debug config
```

### Validation

Validate your JSON:

```bash
# Using Python
python3 -m json.tool opencode.json

# Using jq
jq . opencode.json
```

## Examples

### Example 1: Cost-Optimized Configuration

> ⚠️ **Note:** The Auditor and Planner models below are illustrative of cost-reduction options. Before substituting lite/flash variants for governance agents, read the [Model Selection Principles](#model-selection-principles) section. Flash variants are not recommended for Auditor or Planner in production builds.

```json
{
  "agent": {
    "gadp-builder": {
      "model": "nvidia/qwen/qwen2.5-coder-7b-instruct",
      "description": "Fast, cost-effective code implementation"
    },
    "gadp-auditor": {
      "model": "nvidia/meta/llama-3.3-70b-instruct",
      "description": "Balanced analysis and cost"
    },
    "gadp-planner": {
      "model": "nvidia/qwen/qwen3-next-80b-a3b-thinking",
      "description": "Deep reasoning for architecture"
    }
  }
}
```

### Example 2: Performance-Optimized Configuration

```json
{
  "agent": {
    "gadp-builder": {
      "model": "nvidia/qwen/qwen3-coder-480b-a35b-instruct",
      "additional": {
        "temperature": 0.1
      }
    },
    "gadp-auditor": {
      "model": "nvidia/z-ai/glm5",
      "additional": {
        "temperature": 0.0
      }
    },
    "gadp-planner": {
      "model": "nvidia/deepseek-ai/deepseek-v4-flash",
      "additional": {
        "reasoningEffort": "high",
        "temperature": 0.3
      }
    }
  }
}
```

### Example 3: Multi-Provider Configuration

```json
{
  "agent": {
    "gadp-builder": {
      "model": "nvidia/qwen/qwen3-coder-480b-a35b-instruct"
    },
    "gadp-auditor": {
      "model": "anthropic/claude-sonnet-4-5"
    },
    "gadp-planner": {
      "model": "openai/gpt-5"
    }
  },
  "provider": {
    "nvidia": {
      "options": {
        "apiKey": "nvidia-key"
      }
    },
    "anthropic": {
      "options": {
        "apiKey": "anthropic-key"
      }
    },
    "openai": {
      "options": {
        "apiKey": "openai-key"
      }
    }
  }
}
```

### Example 4: Development vs Production

**Development** (fast iteration):
```json
{
  "agent": {
    "gadp-builder": {
      "model": "nvidia/qwen/qwen2.5-coder-7b-instruct"
    }
  }
}
```

**Production** (quality focus):
```json
{
  "agent": {
    "gadp-builder": {
      "model": "nvidia/qwen/qwen3-coder-480b-a35b-instruct"
    },
    "gadp-auditor": {
      "model": "anthropic/claude-sonnet-4-5"
    }
  }
}
```

## Best Practices

### 1. Model Selection

- **Match model to task**: Use coder models for implementation, reasoning models for planning
- **Consider cost**: Balance quality with budget constraints
- **Test variants**: Experiment with `reasoningEffort` and `temperature`

### 2. Permission Management

- **Principle of least privilege**: Auditor and Planner shouldn't edit files
- **Audit permissions**: Regularly review who can do what
- **Document exceptions**: Note why certain permissions are granted

### 3. Configuration Management

- **Version control**: Commit `opencode.json` to git (exclude API keys)
- **Environment variables**: Use `{env:VAR_NAME}` for sensitive data
- **Multiple environments**: Separate configs for dev/staging/prod

### 4. Testing

- **Test locally**: Verify configuration before committing
- **Monitor costs**: Track usage per agent
- **Fallback plans**: Have backup models configured

### 5. Security

- **Protect API keys**: Never commit actual keys to version control
- **Rotate keys regularly**: Change API keys periodically
- **Audit access**: Review who has access to your provider accounts

## Advanced Topics

### Custom Agents

You can create additional agents beyond the three GADP core agents:

```json
{
  "agent": {
    "gadp-security-reviewer": {
      "description": "Specialized security analysis",
      "mode": "subagent",
      "model": "nvidia/deepseek-ai/deepseek-coder-6.7b-instruct",
      "hidden": true,
      "prompt": "{file:./gadp/agents/security-reviewer.md}",
      "permission": {
        "read": "allow",
        "edit": "deny",
        "bash": "allow",
        "grep": "allow"
      }
    }
  }
}
```

### Agent Chaining

Agents can invoke other agents (if permissions allow):

```json
{
  "agent": {
    "gadp-orchestrator": {
      "permission": {
        "task": {
          "gadp-*": "allow"
        }
      }
    }
  }
}
```

### Dynamic Model Selection

Use environment variables for dynamic model selection:

```json
{
  "agent": {
    "gadp-builder": {
      "model": "{env:BUILDER_MODEL}"
    }
  }
}
```

Set via environment:
```bash
export BUILDER_MODEL="nvidia/qwen/qwen3-coder-480b-a35b-instruct"
opencode
```

## Resources

### Documentation

- [OpenCode Agents Documentation](https://opencode.ai/docs/agents/)
- [OpenCode Config Documentation](https://opencode.ai/docs/config/)
- [GADP Protocol Documentation](./AGENTS.md)
- [models.dev API](https://models.dev/api.json)

### Tools

- [OpenCode CLI](https://opencode.ai/)
- [Claude Code](https://claude.ai/code)
- [models.dev Model Browser](https://models.dev/)

### Community

- [OpenCode Discord](https://opencode.ai/discord)
- [GADP GitHub Issues](https://github.com/anomalyco/gadp/issues)

## Support

For issues specific to:

- **OpenCode configuration**: Check OpenCode documentation and Discord
- **GADP protocol**: Review AGENTS.md and GADP documentation
- **Provider issues**: Contact your model provider's support
- **Harness-specific problems**: Consult your harness documentation

## Changelog

### Version 1.0 (2026-05-01)
- Initial comprehensive configuration guide
- Model selection guidelines
- Agentic harness compatibility matrix
- Troubleshooting section
- Examples and best practices