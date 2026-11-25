import { app } from "../../../scripts/app.js";


const NODE_CLASSES = new Set([
    "PonyToolboxAbsoluteAnySwitch",
]);
const MAX_TRACE_DEPTH = 32;

export const DEFAULT_VISIBLE_ANY_INPUTS = 3;
export const MAX_ANY_INPUTS = 16;
export const ALLOW_MUTED_UPSTREAM_LABEL_ZH =
    "允许上游传递";
export const ALLOW_MUTED_UPSTREAM_LABEL_EN =
    "Allow upstream transfer";


function allowMutedUpstreamLabel() {
    const locale = String(
        app?.ui?.settings?.getSettingValue?.("Comfy.Locale")
        || "en"
    ).toLowerCase();

    return locale.startsWith("zh")
        ? ALLOW_MUTED_UPSTREAM_LABEL_ZH
        : ALLOW_MUTED_UPSTREAM_LABEL_EN;
}


function graphNodeById(graph, id) {
    if (id === undefined || id === null) {
        return null;
    }

    return (
        graph?.getNodeById?.(id)
        ?? graph?.getNodeById?.(Number(id))
        ?? graph?._nodes_by_id?.[id]
        ?? null
    );
}


function graphLinkById(graph, id) {
    if (id === undefined || id === null) {
        return null;
    }

    const links = graph?.links;

    if (!links) {
        return null;
    }

    if (typeof links.get === "function") {
        return (
            links.get(id)
            ?? links.get(String(id))
            ?? links.get(Number(id))
            ?? null
        );
    }

    return links[id] ?? links[String(id)] ?? null;
}


function nodeIsActive(node) {
    return (
        Number(node?.mode ?? 0) === 0
        && node?.flags?.disabled !== true
    );
}


function traceKey(nodeId, outputSlot) {
    return `${nodeId}:${outputSlot ?? ""}`;
}


function normalizedTypes(value) {
    return String(value || "*")
        .split(",")
        .map(type => type.trim().toUpperCase())
        .filter(Boolean);
}


function typesMatch(inputType, outputType) {
    const inputTypes = normalizedTypes(inputType);
    const outputTypes = normalizedTypes(outputType);

    return (
        inputTypes.includes("*")
        || outputTypes.includes("*")
        || inputTypes.some(type => outputTypes.includes(type))
    );
}


function promptLink(value) {
    if (
        !Array.isArray(value)
        || value.length < 2
        || value[0] === null
        || value[0] === undefined
        || !Number.isInteger(Number(value[1]))
    ) {
        return null;
    }

    return [value[0], Number(value[1])];
}


function graphLinkValue(link) {
    if (!link) {
        return null;
    }

    const originId = link.origin_id ?? link.originId ?? link[1];
    const originSlot = (
        link.origin_slot
        ?? link.originSlot
        ?? link[2]
    );

    return originId === undefined || originId === null
        ? null
        : [originId, Number(originSlot) || 0];
}


function booleanWidgetValue(node, name) {
    const named = node?.widgets_values_named?.[name];

    if (typeof named === "boolean") {
        return named;
    }

    const widget = (node?.widgets || [])
        .find(entry => entry?.name === name);

    if (typeof widget?.value === "boolean") {
        return widget.value;
    }

    const values = node?.widgets_values;

    if (typeof values === "object" && values !== null) {
        if (typeof values[name] === "boolean") {
            return values[name];
        }

        if (Array.isArray(values) && typeof values[0] === "boolean") {
            return values[0];
        }
    }

    return false;
}


export function localizeSwitchWidgets(node) {
    const widget = (node?.widgets || []).find(
        entry => entry?.name === "allow_muted_upstream"
    );
    const label = allowMutedUpstreamLabel();

    if (widget) {
        widget.label = label;
    }

    for (const input of node?.inputs || []) {
        if (input?.name === "allow_muted_upstream") {
            input.localized_name = label;
        }
    }

    return node;
}


function branchIsActive(
    node,
    outputSlot,
    getNodeById,
    getGraphLink,
    visited = new Set(),
    depth = 0
) {
    if (!node || depth >= MAX_TRACE_DEPTH) {
        return false;
    }

    const visitKey = traceKey(node.id, outputSlot);

    if (visited.has(visitKey)) {
        return false;
    }

    visited.add(visitKey);

    if (!nodeIsActive(node)) {
        return false;
    }

    if (node.type === "GetNode") {
        const slot = Number(outputSlot) || 0;

        if (typeof node.getInputLink === "function") {
            const source = graphLinkValue(
                node.getInputLink(slot)
            );

            if (source) {
                return branchIsActive(
                    getNodeById(source[0]),
                    source[1],
                    getNodeById,
                    getGraphLink,
                    visited,
                    depth + 1
                );
            }
        }

        if (typeof node.resolveVirtualOutput === "function") {
            const source = node.resolveVirtualOutput(slot);

            if (source?.node) {
                return branchIsActive(
                    source.node,
                    source.slot,
                    getNodeById,
                    getGraphLink,
                    visited,
                    depth + 1
                );
            }
        }

        return false;
    }

    if (node.type === "SetNode" || node.isVirtualNode === true) {
        const source = graphLinkValue(
            getGraphLink(node.inputs?.[0]?.link)
        );

        return branchIsActive(
            source ? getNodeById(source[0]) : null,
            source?.[1],
            getNodeById,
            getGraphLink,
            visited,
            depth + 1
        );
    }

    return true;
}


function specialInputValue(
    node,
    outputSlot,
    getGraphLink
) {
    const slot = Number(outputSlot) || 0;

    if (node.type === "GetNode") {
        if (typeof node.getInputLink === "function") {
            return graphLinkValue(node.getInputLink(slot));
        }

        if (typeof node.resolveVirtualOutput === "function") {
            const source = node.resolveVirtualOutput(slot);

            if (source?.node) {
                return [source.node.id, Number(source.slot) || 0];
            }
        }

        return null;
    }

    if (node.type === "SetNode" || node.isVirtualNode === true) {
        return graphLinkValue(
            getGraphLink(node.inputs?.[0]?.link)
        );
    }

    return null;
}


function resolveTransferableLink(
    prompt,
    link,
    expectedType,
    getNodeById,
    getGraphLink,
    visited = new Set(),
    depth = 0
) {
    const candidate = promptLink(link);

    if (
        !candidate
        || depth >= MAX_TRACE_DEPTH
    ) {
        return null;
    }

    const nodeId = String(candidate[0]);
    const visitKey = traceKey(nodeId, candidate[1]);

    if (visited.has(visitKey)) {
        return null;
    }

    visited.add(visitKey);

    const graphNode = getNodeById(nodeId);

    if (!graphNode) {
        return null;
    }

    const promptNode = prompt[nodeId];

    if (nodeIsActive(graphNode)) {
        if (
            graphNode.type === "GetNode"
            || graphNode.type === "SetNode"
            || graphNode.isVirtualNode === true
        ) {
            const special = specialInputValue(
                graphNode,
                candidate[1],
                getGraphLink
            );

            return special
                ? resolveTransferableLink(
                    prompt,
                    special,
                    expectedType,
                    getNodeById,
                    getGraphLink,
                    visited,
                    depth + 1
                )
                : null;
        }

        return promptNode ? candidate : null;
    }

    for (const input of graphNode.inputs || []) {
        if (input?.link === undefined || input.link === null) {
            continue;
        }

        const sourceLink = getGraphLink(input.link);
        const declaredType = sourceLink?.type || input.type || "*";

        if (!typesMatch(declaredType, expectedType)) {
            continue;
        }

        const promptInput = promptLink(
            promptNode?.inputs?.[input.name]
        ) || graphLinkValue(sourceLink);

        if (!promptInput) {
            continue;
        }

        const resolved = resolveTransferableLink(
            prompt,
            promptInput,
            expectedType,
            getNodeById,
            getGraphLink,
            new Set(visited),
            depth + 1
        );

        if (resolved) {
            return resolved;
        }
    }

    return null;
}


export function filterPrompt(prompt, graphApi) {
    const output = prompt?.output;

    if (
        !output
        || typeof output !== "object"
        || typeof graphApi?.getNodeById !== "function"
        || typeof graphApi?.getGraphLink !== "function"
    ) {
        return;
    }

    for (const [nodeId, promptNode] of Object.entries(output)) {
        if (!NODE_CLASSES.has(promptNode?.class_type)) {
            continue;
        }

        const graphNode = graphApi.getNodeById(nodeId);
        const promptInputs = promptNode.inputs;

        if (
            !graphNode?.inputs
            || !promptInputs
            || typeof promptInputs !== "object"
        ) {
            continue;
        }

        const allowMutedUpstream = booleanWidgetValue(
            graphNode,
            "allow_muted_upstream"
        );
        let firstSelectedInput = null;

        for (const input of graphNode.inputs) {
            if (!input?.name?.startsWith("any_")) {
                continue;
            }

            if (input.link === undefined || input.link === null) {
                continue;
            }

            if (
                !Object.prototype.hasOwnProperty.call(
                    promptInputs,
                    input.name
                )
            ) {
                continue;
            }

            const originalLink = promptLink(
                promptInputs[input.name]
            );

            if (!originalLink) {
                continue;
            }

            const link = graphApi.getGraphLink(input.link);
            const origin = graphApi.getNodeById(
                link?.origin_id ?? originalLink[0]
            );
            const outputSlot = (
                link?.origin_slot
                ?? originalLink[1]
            );
            const expectedType = (
                link?.type
                || input.type
                || "*"
            );
            const selectedLink = allowMutedUpstream
                ? resolveTransferableLink(
                    output,
                    originalLink,
                    expectedType,
                    graphApi.getNodeById,
                    graphApi.getGraphLink
                )
                : branchIsActive(
                    origin,
                    outputSlot,
                    graphApi.getNodeById,
                    graphApi.getGraphLink
                )
                    ? originalLink
                    : null;

            if (!selectedLink) {
                continue;
            }

            firstSelectedInput = {
                name: input.name,
                link: selectedLink,
            };
            break;
        }

        for (const key of Object.keys(promptInputs)) {
            if (key.startsWith("any_")) {
                delete promptInputs[key];
            }
        }

        if (firstSelectedInput) {
            promptInputs[firstSelectedInput.name] = (
                firstSelectedInput.link
            );
        }
    }
}


export function installGraphToPromptFilter(
    graphApp,
    originalGraphToPrompt = graphApp?.graphToPrompt
) {
    if (typeof originalGraphToPrompt !== "function") {
        return originalGraphToPrompt;
    }

    const filteredGraphToPrompt = async function (...args) {
        const result = await originalGraphToPrompt.apply(
            graphApp,
            args
        );

        filterPrompt(result, {
            getNodeById(id) {
                return graphNodeById(graphApp?.graph, id);
            },
            getGraphLink(id) {
                return graphLinkById(graphApp?.graph, id);
            },
        });

        return result;
    };
    filteredGraphToPrompt.__absoluteAnySwitchFiltered = true;

    return filteredGraphToPrompt;
}


function anyInputEntries(node) {
    return (node?.inputs || [])
        .map((input, index) => ({
            input,
            index,
            number: Number(
                String(input?.name || "")
                    .match(/^any_(\d+)$/)?.[1]
            ),
        }))
        .filter(entry => Number.isInteger(entry.number));
}


function addNextAnyInput(node) {
    const used = new Set(
        anyInputEntries(node)
            .map(entry => entry.number)
    );

    for (
        let index = 1;
        index <= MAX_ANY_INPUTS;
        index += 1
    ) {
        if (!used.has(index)) {
            node.addInput(
                `any_${String(index).padStart(2, "0")}`,
                "*"
            );
            return true;
        }
    }

    return false;
}


export function compactAnyInputs(node) {
    if (!node || !Array.isArray(node.inputs)) {
        return;
    }

    while (
        anyInputEntries(node).length
        < DEFAULT_VISIBLE_ANY_INPUTS
    ) {
        if (!addNextAnyInput(node)) {
            break;
        }
    }

    const connectedIndexes = anyInputEntries(node)
        .filter(entry => (
            entry.input.link !== undefined
            && entry.input.link !== null
        ))
        .map(entry => entry.number);
    const highestConnected = connectedIndexes.length
        ? Math.max(...connectedIndexes)
        : 0;
    const desiredCount = Math.min(
        MAX_ANY_INPUTS,
        Math.max(
            DEFAULT_VISIBLE_ANY_INPUTS,
            highestConnected + 1
        )
    );

    while (anyInputEntries(node).length < desiredCount) {
        if (!addNextAnyInput(node)) {
            break;
        }
    }

    for (
        let index = node.inputs.length - 1;
        index >= 0;
        index -= 1
    ) {
        const input = node.inputs[index];
        const number = Number(
            String(input?.name || "")
                .match(/^any_(\d+)$/)?.[1]
        );

        if (
            !Number.isInteger(number)
            || number <= desiredCount
            || (
                input.link !== undefined
                && input.link !== null
            )
        ) {
            continue;
        }

        node.removeInput(index);
    }

    const width = node.size?.[0] || 210;
    const height = node.computeSize?.()[1];

    if (height) {
        node.setSize?.([width, height]);
    }

    node.setDirtyCanvas?.(true, true);
}
