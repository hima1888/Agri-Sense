import { events as defaultEvents, type RootState } from '@react-three/fiber'

/**
 * R3F's default event manager derives the pointer from event.offsetX/Y, which is wrong
 * under CSS transforms (our page transition) and with a device-scale factor (offsets come
 * back in a different space, so clicks pick the wrong object). Map clientX/Y against the
 * canvas's bounding rect instead: both are in the same CSS space in every case.
 */
export function clientRectEvents(store: Parameters<typeof defaultEvents>[0]) {
  const base = defaultEvents(store)
  return {
    ...base,
    compute(event: { clientX: number; clientY: number }, state: RootState) {
      state.pointer.set(...clientToNdc(event.clientX, event.clientY, state.gl.domElement.getBoundingClientRect()))
      state.raycaster.setFromCamera(state.pointer, state.camera)
    },
  }
}

/** The pointer maths on its own, for testing: CSS client coordinates -> normalised device coordinates. */
export function clientToNdc(clientX: number, clientY: number, rect: { left: number; top: number; width: number; height: number }): [number, number] {
  return [((clientX - rect.left) / rect.width) * 2 - 1, -((clientY - rect.top) / rect.height) * 2 + 1]
}
