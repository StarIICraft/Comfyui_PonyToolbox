import { app } from "../../../scripts/app.js";
import {
    compactAnyInputs,
    installGraphToPromptFilter,
    localizeSwitchWidgets,
} from "./absolute_any_switch_core.js";


const NODE_CLASSES = new Set([
    "PonyToolboxAbsoluteAnySwitch",
]);


function installPromptFilter() {
    if (app.graphToPrompt?.__absoluteAnySwitchFiltered) {
        return;
    }

    app.graphToPrompt = installGraphToPromptFilter(
        app,
        app.graphToPrompt,
    );
}


function scheduleCompact(node) {
    if (!node) {
        return;
    }

    clearTimeout(node.__absoluteSwitchCompactTimer);
    node.__absoluteSwitchCompactTimer = setTimeout(
        () => {
            node.__absoluteSwitchCompactTimer = null;
            compactAnyInputs(node);
        },
        0
    );
}


app.registerExtension({
    name: "PonyToolbox.AbsoluteAnySwitch",

    setup() {
        installPromptFilter();
    },

    async beforeRegisterNodeDef(
        nodeType,
        nodeData
    ) {
        if (!NODE_CLASSES.has(nodeData?.name)) {
            return;
        }

        const originalCreated =
            nodeType.prototype.onNodeCreated;
        const originalConfigure =
            nodeType.prototype.onConfigure;
        const originalConnectionsChange =
            nodeType.prototype.onConnectionsChange;

        nodeType.prototype.onNodeCreated =
            function () {
                const result = originalCreated?.apply(
                    this,
                    arguments
                );

                localizeSwitchWidgets(this);
                scheduleCompact(this);
                return result;
            };

        nodeType.prototype.onConfigure =
            function () {
                const result = originalConfigure?.apply(
                    this,
                    arguments
                );

                localizeSwitchWidgets(this);
                scheduleCompact(this);
                return result;
            };

        nodeType.prototype.onConnectionsChange =
            function () {
                const result =
                    originalConnectionsChange?.apply(
                        this,
                        arguments
                    );

                scheduleCompact(this);
                return result;
            };
    },
});
