import { app } from "../../../scripts/app.js";


const NODE_TYPE = "PonyToolboxAdvancedTextConcat";
const DEFAULT_TEXT_ROWS = 2;
const MIN_TEXT_ROWS = 1;
const MAX_TEXT_ROWS = 32;
const SCHEMA_VERSION = 2;
const DOM_WIDGET_NAME = "__pony_text_rows_ui";
const TEXT_NAME = /^text(\d+)$/;
const ROW_GAP = 8;
const ROW_LABEL_HEIGHT = 13;
const ROW_CONTENT_GAP = 3;
const TEXTAREA_HEIGHT = 58;
const CONNECTED_ROW_HEIGHT = 28;
const CONTAINER_PADDING_TOP = 2;
const SLOT_VERTICAL_INSET = 7;

const LEGACY_TEXT_WIDGET_INDEX = {
    1: 0,
    2: 1,
    3: 2,
    4: 4,
    5: 5,
};


function isChineseLocale() {
    return String(
        app?.ui?.settings?.getSettingValue?.("Comfy.Locale")
        || "en"
    ).toLowerCase().startsWith("zh");
}


function labels() {
    if (isChineseLocale()) {
        return {
            placeholder: "— 文本行操作 —",
            add: "增加文本行",
            deleteLast: index => `删除文本行 ${index}`,
            maxRows: `已达到最大行数（${MAX_TEXT_ROWS}）`,
            row: index => `文本行 ${index}`,
            connected: "已连接",
            textareaTooltip: index => (
                `第 ${index} 行的多行文本；连接输入后使用上游字符串。`
            ),
        };
    }
    return {
        placeholder: "— Text row actions —",
        add: "Add text row",
        deleteLast: index => `Delete text row ${index}`,
        maxRows: `Maximum rows reached (${MAX_TEXT_ROWS})`,
        row: index => `Text row ${index}`,
        connected: "Connected",
        textareaTooltip: index => (
            `Multiline text for row ${index}; upstream text is used when connected.`
        ),
    };
}


function findWidget(node, name) {
    return node?.widgets?.find(widget => widget?.name === name) || null;
}


function rowIndex(item) {
    const match = TEXT_NAME.exec(String(item?.name || ""));
    return match ? Number(match[1]) : 0;
}


function inputConnected(node, input, index) {
    return !!(
        input
        && (
            node?.getInputLink?.(index)
            || node?.isInputConnected?.(index)
        )
    );
}


function rowConnected(node, index) {
    return (node?.inputs || []).some((input, slot) => (
        rowIndex(input) === index
        && inputConnected(node, input, slot)
    ));
}


function connectedRows(node) {
    let count = 0;
    (node?.inputs || []).forEach((input, index) => {
        if (inputConnected(node, input, index)) {
            count = Math.max(count, rowIndex(input));
        }
    });
    return count;
}


function storedRows(node) {
    const value = Number(node?.properties?.ponyTextRows);
    return Number.isFinite(value) ? value : 0;
}


function rowCount(node) {
    return Math.min(
        MAX_TEXT_ROWS,
        Math.max(MIN_TEXT_ROWS, storedRows(node), connectedRows(node))
    );
}


function hideBackendWidget(widget) {
    if (!widget) {
        return;
    }
    if (widget.__ponyHiddenSaved) {
        return;
    }
    widget.__ponyHiddenSaved = true;
    widget.__ponyHiddenType = widget.type;
    widget.__ponyHiddenComputeSize = widget.computeSize;
    widget.type = "hidden";
    widget.hidden = true;
    widget.options ||= {};
    widget.options.hidden = true;
    widget.computeSize = () => [0, -4];
    if (widget.element) {
        widget.element.style.display = "none";
    }
    if (widget.inputEl) {
        widget.inputEl.style.display = "none";
    }
}


function hideBackendTextWidgets(node) {
    for (let index = 1; index <= MAX_TEXT_ROWS; index += 1) {
        hideBackendWidget(findWidget(node, `text${index}`));
    }
}


function ensureInput(node, index, text) {
    const name = `text${index}`;
    let input = node.inputs?.find(item => item?.name === name);
    if (!input) {
        input = node.addInput(name, "STRING", {
            label: text.row(index),
            tooltip: text.textareaTooltip(index),
            widget: { name },
        });
    }
    input.type = "STRING";
    input.widget ||= { name };
    input.label = text.row(index);
    input.tooltip = text.textareaTooltip(index);
    return input;
}


function reorderInputs(node, count) {
    const links = new Map();
    node.inputs.forEach((input, index) => {
        const id = node.getInputLink?.(index)?.id ?? null;
        if (id != null) {
            links.set(input, id);
        }
    });

    const textInputs = [];
    for (let index = 1; index <= count; index += 1) {
        textInputs.push(ensureInput(node, index, labels()));
    }
    const others = node.inputs.filter(input => !TEXT_NAME.test(input?.name || ""));
    node.inputs.splice(
        0,
        node.inputs.length,
        ...textInputs,
        ...others
    );

    node.inputs.forEach((input, index) => {
        const id = links.get(input);
        if (id == null) {
            return;
        }
        const link = (
            node.graph?.links?.get?.(id)
            ?? node.graph?.links?.[id]
        );
        if (link) {
            link.target_slot = index;
        }
    });
}


function removeUnusedInputs(node, count) {
    for (let index = node.inputs.length - 1; index >= 0; index -= 1) {
        const input = node.inputs[index];
        if (
            rowIndex(input) > count
            && !inputConnected(node, input, index)
        ) {
            node.removeInput(index);
        }
    }
}


function styleTextarea(element) {
    Object.assign(element.style, {
        width: "100%",
        height: `${TEXTAREA_HEIGHT}px`,
        minHeight: `${TEXTAREA_HEIGHT}px`,
        resize: "vertical",
        boxSizing: "border-box",
        color: "var(--input-text, #ddd)",
        background: "var(--comfy-input-bg, #262626)",
        border: "1px solid var(--border-color, #444)",
        borderRadius: "5px",
        padding: "6px 8px",
        font: "12px/1.4 monospace",
        pointerEvents: "auto",
    });
}


function ensureDomWidget(node) {
    let widget = node.__ponyDomWidget;
    if (widget) {
        return widget;
    }

    const container = document.createElement("div");
    Object.assign(container.style, {
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        width: "100%",
        padding: "2px 0",
        pointerEvents: "none",
    });

    widget = node.addDOMWidget(
        DOM_WIDGET_NAME,
        "PONY_TEXT_ROWS",
        container,
        {
            serialize: false,
            hideOnZoom: false,
            getMinHeight: () => node.__ponyDomHeight || 160,
            getMaxHeight: () => node.__ponyDomHeight || 160,
        }
    );
    widget.serialize = false;
    widget.options ||= {};
    widget.options.serialize = false;
    widget.element = container;
    container.dataset.testid = "pony-text-rows";
    node.__ponyDomWidget = widget;
    node.__ponyDomContainer = container;
    return widget;
}


function buildRowsUi(node, count) {
    const text = labels();
    const container = node.__ponyDomContainer;
    container.replaceChildren();

    for (let index = 1; index <= count; index += 1) {
        const row = document.createElement("div");
        row.dataset.ponyTextRow = String(index);
        Object.assign(row.style, {
            position: "relative",
            display: "flex",
            flexDirection: "column",
            gap: `${ROW_CONTENT_GAP}px`,
            paddingLeft: "12px",
        });

        const label = document.createElement("div");
        label.textContent = text.row(index);
        Object.assign(label.style, {
            height: `${ROW_LABEL_HEIGHT}px`,
            lineHeight: `${ROW_LABEL_HEIGHT}px`,
            fontSize: "11px",
            color: "var(--descrip-text, #999)",
        });
        row.appendChild(label);

        if (rowConnected(node, index)) {
            const connected = document.createElement("div");
            connected.textContent = text.connected;
            Object.assign(connected.style, {
                height: `${CONNECTED_ROW_HEIGHT}px`,
                minHeight: `${CONNECTED_ROW_HEIGHT}px`,
                display: "flex",
                alignItems: "center",
                padding: "0 8px",
                borderRadius: "5px",
                background: "var(--comfy-input-bg, #262626)",
                border: "1px solid var(--border-color, #444)",
                fontSize: "12px",
                color: "var(--descrip-text, #999)",
            });
            row.appendChild(connected);
        } else {
            const source = findWidget(node, `text${index}`);
            const input = document.createElement("textarea");
            input.value = source?.value ?? "";
            input.placeholder = `text${index}`;
            input.title = text.textareaTooltip(index);
            styleTextarea(input);
            input.addEventListener("input", () => {
                if (source) {
                    source.value = input.value;
                }
                node.setDirtyCanvas?.(true, true);
            });
            row.appendChild(input);
        }
        container.appendChild(row);
    }

    const action = document.createElement("select");
    for (const value of actionOptions(node, count)) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        action.appendChild(option);
    }
    action.value = text.placeholder;
    Object.assign(action.style, {
        width: "100%",
        height: "28px",
        color: "var(--input-text, #ddd)",
        background: "var(--comfy-input-bg, #262626)",
        border: "1px solid var(--border-color, #444)",
        borderRadius: "5px",
        padding: "0 6px",
        pointerEvents: "auto",
    });
    action.addEventListener("change", () => {
        const value = action.value;
        action.value = labels().placeholder;
        handleAction(node, value);
    });
    container.appendChild(action);

    const visibleRows = count;
    const connectedCount = Array.from(
        { length: count },
        (_, index) => index + 1
    ).filter(index => rowConnected(node, index)).length;
    node.__ponyDomHeight = Math.max(
        96,
        visibleRows * 91 + connectedCount * (28 - 58) + 32
    );
    node.__ponyDomWidget.computeSize = width => [
        width,
        node.__ponyDomHeight,
    ];
    container.style.minHeight = `${node.__ponyDomHeight}px`;
    node.graph?.setDirtyCanvas?.(true, true);
}


function actionOptions(node, count) {
    const text = labels();
    const values = [
        text.placeholder,
        count < MAX_TEXT_ROWS ? text.add : text.maxRows,
    ];
    if (
        count > MIN_TEXT_ROWS
        && !rowConnected(node, count)
    ) {
        values.push(text.deleteLast(count));
    }
    return values;
}


function alignTextInputs(node, count) {
    const rows = new Map(
        Array.from(
            node.__ponyDomContainer?.querySelectorAll?.(
                "[data-pony-text-row]"
            ) || []
        ).map(row => [
            Number(row.dataset.ponyTextRow),
            row,
        ])
    );
    const widgetTop = Number(
        node.__ponyDomWidget?.y
        ?? node.__ponyDomWidget?.last_y
        ?? 0
    );
    let fallbackTop = CONTAINER_PADDING_TOP;

    for (let index = 1; index <= count; index += 1) {
        const inputIndex = node.inputs.findIndex(
            input => input?.name === `text${index}`
        );
        if (inputIndex === -1) {
            continue;
        }

        const row = rows.get(index);
        const measuredHeight = Number(row?.offsetHeight || 0);
        const measuredTop = Number(row?.offsetTop || 0);
        const rowTop = measuredHeight > 0
            ? measuredTop
            : fallbackTop;
        const rowHeight = measuredHeight > 0
            ? measuredHeight
            : (
                ROW_LABEL_HEIGHT
                + ROW_CONTENT_GAP
                + (
                    rowConnected(node, index)
                        ? CONNECTED_ROW_HEIGHT
                        : TEXTAREA_HEIGHT
                )
            );

        const slotY = (
            widgetTop
            + rowTop
            + Math.min(SLOT_VERTICAL_INSET, rowHeight / 2)
        );
        const backendWidget = findWidget(node, `text${index}`);
        if (backendWidget) {
            // ComfyUI re-derives widget-backed slot positions on every
            // arrange(), using widget.y + half a 20px slot.
            backendWidget.y = slotY - 10;
        }
        node.inputs[inputIndex].pos = [10, slotY];
        fallbackTop += rowHeight + ROW_GAP;
    }
}


function queueInputAlignment(node, count) {
    if (node.__ponyAlignFrame != null) {
        cancelAnimationFrame(node.__ponyAlignFrame);
    }
    node.__ponyAlignFrame = requestAnimationFrame(() => {
        node.__ponyAlignFrame = null;
        if (!node.graph) {
            return;
        }
        alignTextInputs(node, count);
        node.setDirtyCanvas?.(true, true);
    });
}


function reorderDomWidget(node) {
    const widget = node.__ponyDomWidget;
    if (!widget) {
        return;
    }
    const index = node.widgets.indexOf(widget);
    if (index !== -1) {
        node.widgets.splice(index, 1);
    }
    const delimiter = node.widgets.findIndex(
        item => item?.name === "delimiter"
    );
    node.widgets.splice(
        delimiter === -1 ? 0 : delimiter,
        0,
        widget
    );
}


function resizeNode(node) {
    const computed = node.computeSize?.();
    if (Array.isArray(computed)) {
        node.setSize([
            Math.max(node.size[0], computed[0]),
            Math.max(computed[1], 140),
        ]);
    }
}


function syncRows(node) {
    if (!node?.graph) {
        return;
    }
    if (node.__ponySyncing) {
        node.__ponySyncAgain = true;
        return;
    }
    node.__ponySyncing = true;
    try {
        const count = rowCount(node);
        node.properties ||= {};
        node.properties.ponyTextRows = count;
        node.properties.ponyTextSchemaVersion = SCHEMA_VERSION;

        hideBackendTextWidgets(node);
        for (let index = 1; index <= count; index += 1) {
            ensureInput(node, index, labels());
        }
        removeUnusedInputs(node, count);
        reorderInputs(node, count);

        ensureDomWidget(node);
        buildRowsUi(node, count);
        reorderDomWidget(node);
        resizeNode(node);
        alignTextInputs(node, count);
        queueInputAlignment(node, count);
        node.setDirtyCanvas?.(true, true);
    } finally {
        node.__ponySyncing = false;
        if (node.__ponySyncAgain) {
            node.__ponySyncAgain = false;
            setTimeout(() => syncRows(node), 0);
        }
    }
}


function scheduleSyncRows(node) {
    if (!node || node.__ponySyncScheduled) {
        return;
    }
    node.__ponySyncScheduled = true;
    setTimeout(() => {
        node.__ponySyncScheduled = false;
        syncRows(node);
    }, 0);
}


function addRow(node) {
    const count = rowCount(node);
    if (count >= MAX_TEXT_ROWS) {
        return;
    }
    node.properties ||= {};
    node.properties.ponyTextRows = count + 1;
    syncRows(node);
}


function deleteRow(node) {
    const count = rowCount(node);
    if (count <= MIN_TEXT_ROWS || rowConnected(node, count)) {
        syncRows(node);
        return;
    }
    const source = findWidget(node, `text${count}`);
    if (source) {
        source.value = "";
    }
    node.properties ||= {};
    node.properties.ponyTextRows = count - 1;
    syncRows(node);
}


function handleAction(node, value) {
    const text = labels();
    const count = rowCount(node);
    if (value === text.add) {
        addRow(node);
    } else if (
        value === text.deleteLast(count)
        && !rowConnected(node, count)
    ) {
        deleteRow(node);
    }
    node.graph?.change?.();
}


function migrateValues(info) {
    if (
        !info
        || info.properties?.ponyTextSchemaVersion === SCHEMA_VERSION
        || !Array.isArray(info.widgets_values)
    ) {
        return;
    }
    const old = info.widgets_values;
    if (old.length === MAX_TEXT_ROWS + 2) {
        return;
    }
    const values = [];
    for (let index = 1; index <= 5; index += 1) {
        values.push(old[LEGACY_TEXT_WIDGET_INDEX[index]] ?? "");
    }
    for (let index = 6; index <= MAX_TEXT_ROWS; index += 1) {
        values.push(old[index + 6] ?? "");
    }
    info.widgets_values = [
        ...values,
        old[3] ?? " ",
        old[11] ?? true,
    ];
    info.properties ||= {};
    info.properties.ponyTextSchemaVersion = SCHEMA_VERSION;
}


function setupNode(node) {
    if (!node || node.__ponyReady) {
        return;
    }
    node.__ponyReady = true;
    node.properties ||= {};
    if (!storedRows(node)) {
        node.properties.ponyTextRows = DEFAULT_TEXT_ROWS;
    }
    node.properties.ponyTextSchemaVersion = SCHEMA_VERSION;
    hideBackendTextWidgets(node);

    const waitForGraph = () => {
        if (!node.graph) {
            setTimeout(waitForGraph, 16);
            return;
        }
        ensureDomWidget(node);
        ensureInput(node, 1, labels());
        ensureInput(node, 2, labels());
        reorderDomWidget(node);
        syncRows(node);
    };
    setTimeout(waitForGraph, 0);
}


app.registerExtension({
    name: "PonyToolbox.AdvancedTextConcat",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name !== NODE_TYPE) {
            return;
        }

        const oldConfigure = nodeType.prototype.configure;
        nodeType.prototype.configure = function (info) {
            migrateValues(info);
            const result = oldConfigure?.apply(this, arguments);
            setTimeout(() => setupNode(this), 0);
            return result;
        };

        const oldNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = oldNodeCreated?.apply(this, arguments);
            setupNode(this);
            return result;
        };

        const oldConfigureNode = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = oldConfigureNode?.apply(this, arguments);
            scheduleSyncRows(this);
            return result;
        };

        const oldConnectionsChange =
            nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (
            type,
            index
        ) {
            const result =
                oldConnectionsChange?.apply(this, arguments);
            if (type === 1 && rowIndex(this.inputs?.[index])) {
                scheduleSyncRows(this);
            }
            return result;
        };
    },
});
