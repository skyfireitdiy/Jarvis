import { ref } from "vue";

export function useDrag() {
  const PANEL_DRAG_ACTIVATION_DISTANCE = 4;
  const EDITOR_PANEL_MIN_WIDTH = 360;
  const EDITOR_PANEL_MIN_HEIGHT = 260;
  const TERMINAL_PANEL_MIN_WIDTH = 400;
  const TERMINAL_PANEL_MIN_HEIGHT = 300;

  function clamp(value, min, max) {
    if (max < min) return min;
    return Math.min(Math.max(value, min), max);
  }

  // 侧边栏拖拽功能
  const sidebarPosition = ref({ x: 20, y: 100 });
  const isDraggingSidebar = ref(false);
  const dragOffset = ref({ x: 0, y: 0 });

  function startDragSidebar(event) {
    isDraggingSidebar.value = true;
    dragOffset.value = {
      x: event.clientX - sidebarPosition.value.x,
      y: event.clientY - sidebarPosition.value.y,
    };
    document.addEventListener("mousemove", onDragSidebar);
    document.addEventListener("mouseup", stopDragSidebar);
  }

  function onDragSidebar(event) {
    if (!isDraggingSidebar.value) return;
    sidebarPosition.value = {
      x: event.clientX - dragOffset.value.x,
      y: event.clientY - dragOffset.value.y,
    };
  }

  function stopDragSidebar() {
    isDraggingSidebar.value = false;
    document.removeEventListener("mousemove", onDragSidebar);
    document.removeEventListener("mouseup", stopDragSidebar);
  }

  // Agent侧边栏调整大小
  const agentSidebarResizeState = ref({
    active: false,
    startX: 0,
    startWidth: 280,
  });

  function startAgentSidebarResize(event, currentWidth) {
    agentSidebarResizeState.value = {
      active: true,
      startX: event.clientX,
      startWidth: currentWidth,
    };
    document.addEventListener("mousemove", onAgentSidebarResize);
    document.addEventListener("mouseup", stopAgentSidebarResize);
    event.preventDefault();
    event.stopPropagation();
  }

  function onAgentSidebarResize(event, normalizeWidth) {
    if (!agentSidebarResizeState.value.active)
      return agentSidebarResizeState.value.startWidth;
    const deltaX = event.clientX - agentSidebarResizeState.value.startX;
    return normalizeWidth(agentSidebarResizeState.value.startWidth + deltaX);
  }

  function stopAgentSidebarResize(saveWidth) {
    if (!agentSidebarResizeState.value.active) {
      document.removeEventListener("mousemove", onAgentSidebarResize);
      document.removeEventListener("mouseup", stopAgentSidebarResize);
      return;
    }
    agentSidebarResizeState.value = {
      active: false,
      startX: 0,
      startWidth: agentSidebarResizeState.value.startWidth,
    };
    document.removeEventListener("mousemove", onAgentSidebarResize);
    document.removeEventListener("mouseup", stopAgentSidebarResize);
    if (saveWidth) saveWidth();
  }

  // 编辑器面板交互功能
  const editorPanelInteraction = ref({
    active: false,
    mode: null,
    direction: null,
    startX: 0,
    startY: 0,
    startTop: 0,
    startLeft: 0,
    startWidth: 0,
    startHeight: 0,
  });

  function getEditorPanelBounds(editorPanelRect) {
    const KEEP_VISIBLE = 100;
    return {
      minTop: KEEP_VISIBLE - editorPanelRect.height,
      minLeft: KEEP_VISIBLE - editorPanelRect.width,
      maxLeft: window.innerWidth - KEEP_VISIBLE,
      maxTop: window.innerHeight - KEEP_VISIBLE,
      maxWidth: window.innerWidth,
      maxHeight: window.innerHeight,
    };
  }

  function ensureEditorPanelInViewport(editorPanelRect) {
    const KEEP_VISIBLE = 100;
    const maxWidth = Math.max(window.innerWidth, EDITOR_PANEL_MIN_WIDTH);
    const maxHeight = Math.max(window.innerHeight, EDITOR_PANEL_MIN_HEIGHT);
    const newRect = { ...editorPanelRect };
    newRect.width = clamp(newRect.width, EDITOR_PANEL_MIN_WIDTH, maxWidth);
    newRect.height = clamp(newRect.height, EDITOR_PANEL_MIN_HEIGHT, maxHeight);
    newRect.left = clamp(
      newRect.left,
      KEEP_VISIBLE - newRect.width,
      window.innerWidth - KEEP_VISIBLE,
    );
    newRect.top = clamp(
      newRect.top,
      KEEP_VISIBLE - newRect.height,
      window.innerHeight - KEEP_VISIBLE,
    );
    return newRect;
  }

  function startEditorPanelMove(event, editorPanelRect, focusWindow) {
    if (window.innerWidth <= 768) return;
    if (event.target.closest(".editor-panel-actions")) return;
    if (focusWindow) focusWindow("editor");
    editorPanelInteraction.value = {
      active: false,
      mode: "move",
      direction: null,
      startX: event.clientX,
      startY: event.clientY,
      startTop: editorPanelRect.top,
      startLeft: editorPanelRect.left,
      startWidth: editorPanelRect.width,
      startHeight: editorPanelRect.height,
    };
    document.addEventListener("mousemove", onEditorPanelPointerMove);
    document.addEventListener("mouseup", stopEditorPanelInteraction);
  }

  function startEditorPanelResize(event, direction, editorPanelRect) {
    if (window.innerWidth <= 768) return;
    editorPanelInteraction.value = {
      active: true,
      mode: "resize",
      direction,
      startX: event.clientX,
      startY: event.clientY,
      startTop: editorPanelRect.top,
      startLeft: editorPanelRect.left,
      startWidth: editorPanelRect.width,
      startHeight: editorPanelRect.height,
    };
    document.addEventListener("mousemove", onEditorPanelPointerMove);
    document.addEventListener("mouseup", stopEditorPanelInteraction);
    event.preventDefault();
    event.stopPropagation();
  }

  function onEditorPanelPointerMove(event, currentRect) {
    const deltaX = event.clientX - editorPanelInteraction.value.startX;
    const deltaY = event.clientY - editorPanelInteraction.value.startY;
    if (
      editorPanelInteraction.value.mode === "move" &&
      !editorPanelInteraction.value.active
    ) {
      if (Math.hypot(deltaX, deltaY) < PANEL_DRAG_ACTIVATION_DISTANCE)
        return currentRect;
      editorPanelInteraction.value = {
        ...editorPanelInteraction.value,
        active: true,
      };
      event.preventDefault();
    }
    if (!editorPanelInteraction.value.active) return currentRect;
    if (editorPanelInteraction.value.mode === "move") {
      const bounds = getEditorPanelBounds(currentRect);
      return {
        ...currentRect,
        left: clamp(
          editorPanelInteraction.value.startLeft + deltaX,
          bounds.minLeft,
          bounds.maxLeft,
        ),
        top: clamp(
          editorPanelInteraction.value.startTop + deltaY,
          bounds.minTop,
          bounds.maxTop,
        ),
      };
    }
    const direction = editorPanelInteraction.value.direction || "";
    const { startLeft, startTop, startWidth, startHeight } =
      editorPanelInteraction.value;
    let nextLeft = startLeft,
      nextTop = startTop,
      nextWidth = startWidth,
      nextHeight = startHeight;
    if (direction.includes("e"))
      nextWidth = clamp(
        startWidth + deltaX,
        EDITOR_PANEL_MIN_WIDTH,
        Math.max(window.innerWidth - startLeft, EDITOR_PANEL_MIN_WIDTH),
      );
    if (direction.includes("s"))
      nextHeight = clamp(
        startHeight + deltaY,
        EDITOR_PANEL_MIN_HEIGHT,
        Math.max(window.innerHeight - startTop, EDITOR_PANEL_MIN_HEIGHT),
      );
    if (direction.includes("w")) {
      const desiredLeft = clamp(
        startLeft + deltaX,
        0,
        startLeft + startWidth - EDITOR_PANEL_MIN_WIDTH,
      );
      nextLeft = desiredLeft;
      nextWidth = startWidth - (desiredLeft - startLeft);
    }
    if (direction.includes("n")) {
      const desiredTop = clamp(
        startTop + deltaY,
        0,
        startTop + startHeight - EDITOR_PANEL_MIN_HEIGHT,
      );
      nextTop = desiredTop;
      nextHeight = startHeight - (desiredTop - startTop);
    }
    if (nextLeft + nextWidth > window.innerWidth)
      nextWidth = Math.max(
        EDITOR_PANEL_MIN_WIDTH,
        window.innerWidth - nextLeft,
      );
    if (nextTop + nextHeight > window.innerHeight)
      nextHeight = Math.max(
        EDITOR_PANEL_MIN_HEIGHT,
        window.innerHeight - nextTop,
      );
    return {
      left: clamp(nextLeft, 0, Math.max(window.innerWidth - nextWidth, 0)),
      top: clamp(nextTop, 0, Math.max(window.innerHeight - nextHeight, 0)),
      width: clamp(
        nextWidth,
        EDITOR_PANEL_MIN_WIDTH,
        Math.max(window.innerWidth - nextLeft, EDITOR_PANEL_MIN_WIDTH),
      ),
      height: clamp(
        nextHeight,
        EDITOR_PANEL_MIN_HEIGHT,
        Math.max(window.innerHeight - nextTop, EDITOR_PANEL_MIN_HEIGHT),
      ),
    };
  }

  function stopEditorPanelInteraction(saveRect, currentRect) {
    editorPanelInteraction.value = {
      active: false,
      mode: null,
      direction: null,
      startX: 0,
      startY: 0,
      startTop: 0,
      startLeft: 0,
      startWidth: 0,
      startHeight: 0,
    };
    document.removeEventListener("mousemove", onEditorPanelPointerMove);
    document.removeEventListener("mouseup", stopEditorPanelInteraction);
    if (saveRect && currentRect) saveRect(currentRect);
  }

  // 终端面板交互功能
  const terminalPanelInteraction = ref({
    active: false,
    mode: null,
    direction: null,
    startX: 0,
    startY: 0,
    startTop: 0,
    startLeft: 0,
    startWidth: 0,
    startHeight: 0,
  });

  function getTerminalPanelBounds(terminalPanelRect) {
    const KEEP_VISIBLE = 100;
    return {
      minTop: KEEP_VISIBLE - terminalPanelRect.height,
      minLeft: KEEP_VISIBLE - terminalPanelRect.width,
      maxLeft: window.innerWidth - KEEP_VISIBLE,
      maxTop: window.innerHeight - KEEP_VISIBLE,
    };
  }

  function ensureTerminalPanelInViewport(terminalPanelRect) {
    const KEEP_VISIBLE = 100;
    const maxWidth = Math.max(window.innerWidth, TERMINAL_PANEL_MIN_WIDTH);
    const maxHeight = Math.max(window.innerHeight, TERMINAL_PANEL_MIN_HEIGHT);
    const newRect = { ...terminalPanelRect };
    newRect.width = clamp(newRect.width, TERMINAL_PANEL_MIN_WIDTH, maxWidth);
    newRect.height = clamp(
      newRect.height,
      TERMINAL_PANEL_MIN_HEIGHT,
      maxHeight,
    );
    newRect.left = clamp(
      newRect.left,
      KEEP_VISIBLE - newRect.width,
      window.innerWidth - KEEP_VISIBLE,
    );
    newRect.top = clamp(
      newRect.top,
      KEEP_VISIBLE - newRect.height,
      window.innerHeight - KEEP_VISIBLE,
    );
    return newRect;
  }

  function startTerminalPanelMove(event, terminalPanelRect, focusWindow) {
    if (window.innerWidth <= 768) return;
    if (event.target.closest(".terminal-panel-actions")) return;
    if (focusWindow) focusWindow("terminal");
    terminalPanelInteraction.value = {
      active: false,
      mode: "move",
      direction: null,
      startX: event.clientX,
      startY: event.clientY,
      startTop: terminalPanelRect.top,
      startLeft: terminalPanelRect.left,
      startWidth: terminalPanelRect.width,
      startHeight: terminalPanelRect.height,
    };
    document.addEventListener("mousemove", onTerminalPanelPointerMove);
    document.addEventListener("mouseup", stopTerminalPanelInteraction);
  }

  function startTerminalPanelResize(event, direction, terminalPanelRect) {
    if (window.innerWidth <= 768) return;
    terminalPanelInteraction.value = {
      active: true,
      mode: "resize",
      direction,
      startX: event.clientX,
      startY: event.clientY,
      startTop: terminalPanelRect.top,
      startLeft: terminalPanelRect.left,
      startWidth: terminalPanelRect.width,
      startHeight: terminalPanelRect.height,
    };
    document.addEventListener("mousemove", onTerminalPanelPointerMove);
    document.addEventListener("mouseup", stopTerminalPanelInteraction);
    event.preventDefault();
    event.stopPropagation();
  }

  function onTerminalPanelPointerMove(event, currentRect) {
    const deltaX = event.clientX - terminalPanelInteraction.value.startX;
    const deltaY = event.clientY - terminalPanelInteraction.value.startY;
    if (
      terminalPanelInteraction.value.mode === "move" &&
      !terminalPanelInteraction.value.active
    ) {
      if (Math.hypot(deltaX, deltaY) < PANEL_DRAG_ACTIVATION_DISTANCE)
        return currentRect;
      terminalPanelInteraction.value = {
        ...terminalPanelInteraction.value,
        active: true,
      };
      event.preventDefault();
    }
    if (!terminalPanelInteraction.value.active) return currentRect;
    if (terminalPanelInteraction.value.mode === "move") {
      const bounds = getTerminalPanelBounds(currentRect);
      return {
        ...currentRect,
        left: clamp(
          terminalPanelInteraction.value.startLeft + deltaX,
          bounds.minLeft,
          bounds.maxLeft,
        ),
        top: clamp(
          terminalPanelInteraction.value.startTop + deltaY,
          bounds.minTop,
          bounds.maxTop,
        ),
      };
    }
    const direction = terminalPanelInteraction.value.direction || "";
    const { startLeft, startTop, startWidth, startHeight } =
      terminalPanelInteraction.value;
    let nextLeft = startLeft,
      nextTop = startTop,
      nextWidth = startWidth,
      nextHeight = startHeight;
    if (direction.includes("e"))
      nextWidth = clamp(
        startWidth + deltaX,
        TERMINAL_PANEL_MIN_WIDTH,
        Math.max(window.innerWidth - startLeft, TERMINAL_PANEL_MIN_WIDTH),
      );
    if (direction.includes("s"))
      nextHeight = clamp(
        startHeight + deltaY,
        TERMINAL_PANEL_MIN_HEIGHT,
        Math.max(window.innerHeight - startTop, TERMINAL_PANEL_MIN_HEIGHT),
      );
    if (direction.includes("w")) {
      const desiredLeft = clamp(
        startLeft + deltaX,
        0,
        startLeft + startWidth - TERMINAL_PANEL_MIN_WIDTH,
      );
      nextLeft = desiredLeft;
      nextWidth = startWidth - (desiredLeft - startLeft);
    }
    if (direction.includes("n")) {
      const desiredTop = clamp(
        startTop + deltaY,
        0,
        startTop + startHeight - TERMINAL_PANEL_MIN_HEIGHT,
      );
      nextTop = desiredTop;
      nextHeight = startHeight - (desiredTop - startTop);
    }
    if (nextLeft + nextWidth > window.innerWidth)
      nextWidth = Math.max(
        TERMINAL_PANEL_MIN_WIDTH,
        window.innerWidth - nextLeft,
      );
    if (nextTop + nextHeight > window.innerHeight)
      nextHeight = Math.max(
        TERMINAL_PANEL_MIN_HEIGHT,
        window.innerHeight - nextTop,
      );
    return {
      left: clamp(nextLeft, 0, Math.max(window.innerWidth - nextWidth, 0)),
      top: clamp(nextTop, 0, Math.max(window.innerHeight - nextHeight, 0)),
      width: clamp(
        nextWidth,
        TERMINAL_PANEL_MIN_WIDTH,
        Math.max(window.innerWidth - nextLeft, TERMINAL_PANEL_MIN_WIDTH),
      ),
      height: clamp(
        nextHeight,
        TERMINAL_PANEL_MIN_HEIGHT,
        Math.max(window.innerHeight - nextTop, TERMINAL_PANEL_MIN_HEIGHT),
      ),
    };
  }

  function stopTerminalPanelInteraction(saveRect, currentRect) {
    terminalPanelInteraction.value = {
      active: false,
      mode: null,
      direction: null,
      startX: 0,
      startY: 0,
      startTop: 0,
      startLeft: 0,
      startWidth: 0,
      startHeight: 0,
    };
    document.removeEventListener("mousemove", onTerminalPanelPointerMove);
    document.removeEventListener("mouseup", stopTerminalPanelInteraction);
    if (saveRect && currentRect) saveRect(currentRect);
  }

  return {
    sidebarPosition,
    isDraggingSidebar,
    startDragSidebar,
    stopDragSidebar,
    agentSidebarResizeState,
    startAgentSidebarResize,
    onAgentSidebarResize,
    stopAgentSidebarResize,
    editorPanelInteraction,
    getEditorPanelBounds,
    ensureEditorPanelInViewport,
    startEditorPanelMove,
    startEditorPanelResize,
    onEditorPanelPointerMove,
    stopEditorPanelInteraction,
    terminalPanelInteraction,
    getTerminalPanelBounds,
    ensureTerminalPanelInViewport,
    startTerminalPanelMove,
    startTerminalPanelResize,
    onTerminalPanelPointerMove,
    stopTerminalPanelInteraction,
  };
}
