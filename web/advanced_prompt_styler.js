import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";


const NODE_TYPE = "PonyToolboxAdvancedPromptStyler";
const ROUTE_PREFIX = "/advanced_prompt_styler";

const WIDGET_LABELS = {
    text_positive: "正向提示词",
    text_negative: "负向提示词",
    style_file: "选择文件",
    style: "样式",
    log_prompt: "输出日志",
    style_name: "样式名称覆盖",
};


function findWidget(node, name) {
    return node?.widgets?.find(widget => widget?.name === name) || null;
}


function widgetValue(widget) {
    return widget?.value == null ? "" : String(widget.value);
}


function setOptions(widget, values, fallback) {
    const options = Array.isArray(values) && values.length
        ? values.filter(value => typeof value === "string")
        : [fallback];

    widget.options ||= {};
    widget.options.values = options;

    if (!options.includes(widgetValue(widget))) {
        widget.value = options[0];
    }
    return widgetValue(widget);
}


function getLink(node, linkId) {
    return (
        node.graph?.getLink?.(linkId)
        || node.graph?.links?.get?.(linkId)
        || node.graph?.links?.[linkId]
        || null
    );
}


function syncPrimitiveStyle(node, styleNames) {
    const styleInput = node.inputs?.find(input => input?.name === "style");
    if (styleInput?.link == null) {
        return;
    }

    const link = getLink(node, styleInput.link);
    const primitive = link
        ? node.graph?.getNodeById?.(link.origin_id)
        : null;
    if (primitive?.type !== "PrimitiveNode") {
        return;
    }

    const output = primitive.outputs?.[link.origin_slot];
    const widgetName = output?.widget?.name || output?.name;
    const widget = (
        primitive.widgets?.find(item => item?.name === widgetName)
        || primitive.widgets?.find(item => Array.isArray(item?.options?.values))
        || primitive.widgets?.[0]
    );
    if (!widget) {
        return;
    }

    setOptions(widget, styleNames, "无可用样式");
    primitive.setDirtyCanvas?.(true, true);
}


async function requestJson(url) {
    const response = await api.fetchApi(url);
    if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
    }
    return await response.json();
}


async function refreshStyles(node) {
    const fileWidget = findWidget(node, "style_file");
    const styleWidget = findWidget(node, "style");
    if (!fileWidget || !styleWidget) {
        return;
    }

    const requestId = Number(node.__advancedStylerRequestId || 0) + 1;
    node.__advancedStylerRequestId = requestId;

    try {
        const fileData = await requestJson(`${ROUTE_PREFIX}/files`);
        if (node.__advancedStylerRequestId !== requestId) {
            return;
        }

        const files = Array.isArray(fileData.files) ? fileData.files : [];
        const file = setOptions(fileWidget, files, "无可用样式文件");
        const styleData = await requestJson(
            `${ROUTE_PREFIX}/styles?file=${encodeURIComponent(file)}`
        );
        if (node.__advancedStylerRequestId !== requestId) {
            return;
        }

        const styleNames = Array.isArray(styleData.styles)
            ? styleData.styles
            : [];
        setOptions(
            styleWidget,
            styleNames,
            "无可用样式"
        );
        syncPrimitiveStyle(node, styleNames);
        node.setDirtyCanvas?.(true, true);
    } catch (error) {
        console.error("刷新提示词风格列表失败：", error);
    }
}


function wrapCallback(widget, callback) {
    if (!widget || widget.__advancedStylerWrapped) {
        return;
    }

    widget.__advancedStylerWrapped = true;
    const oldCallback = widget.callback;
    widget.callback = async function (...args) {
        if (typeof oldCallback === "function") {
            oldCallback.apply(this, args);
        }
        await callback();
    };
}


function setupNode(node) {
    if (!node || node.__advancedStylerSetupDone) {
        return;
    }
    node.__advancedStylerSetupDone = true;

    for (const [name, label] of Object.entries(WIDGET_LABELS)) {
        const widget = findWidget(node, name);
        if (widget) {
            widget.label = label;
        }
    }

    wrapCallback(
        findWidget(node, "style_file"),
        () => refreshStyles(node)
    );

    setTimeout(() => refreshStyles(node), 150);
}


app.registerExtension({
    name: "PonyToolbox.AdvancedPromptStyler",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name !== NODE_TYPE) {
            return;
        }

        const oldOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = oldOnNodeCreated?.apply(this, arguments);
            setupNode(this);
            return result;
        };

        const oldOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = oldOnConfigure?.apply(this, arguments);
            setupNode(this);
            setTimeout(() => refreshStyles(this), 250);
            return result;
        };

        const oldOnConnectionsChange =
            nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const result = oldOnConnectionsChange?.apply(this, arguments);
            setTimeout(() => refreshStyles(this), 0);
            return result;
        };
    },
});
