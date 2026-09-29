# React Native Patterns

Patterns for production React Native apps with Expo. These assume the managed Expo workflow (Expo Router, EAS, `expo-*` modules) and the New Architecture (default in recent Expo SDKs, required from SDK 55+). React core hook rules from the main React standards still apply; this file covers mobile-specific concerns.

## Project Structure (Expo Router)

- File-based routing under `app/`. Keep route files thin — they read and validate params, then delegate to a screen component in `components/` or `features/`.

```
app/
  _layout.tsx           # root stack
  (tabs)/
    _layout.tsx         # tab navigator
    index.tsx           # Home
  user/[id].tsx         # dynamic route
features/
  user/UserProfile.tsx
```

## Route Params: Always Validate

- Deep links and dynamic routes deliver untrusted strings. Validate with Zod before using the value in a query or navigation call.

```tsx
// app/user/[id].tsx
import { useLocalSearchParams, router } from 'expo-router'
import { z } from 'zod'

const Params = z.object({ id: z.string().uuid() })

export default function UserRoute() {
  const parsed = Params.safeParse(useLocalSearchParams())
  if (!parsed.success) {
    router.replace('/not-found')
    return null
  }
  return <UserProfile userId={parsed.data.id} />
}
```

## State: Keep Concerns Separate

- Do not duplicate server data into a client store. Each concern has one home.

| Concern | Tool |
|---|---|
| Server/remote data | TanStack Query, SWR |
| Client/UI state | Zustand, Jotai, or Context |
| Route/navigation state | Expo Router params |
| Form state | React Hook Form + Zod resolver |
| Secrets and tokens | `expo-secure-store` |
| Non-secret persistence | AsyncStorage / MMKV |

- Start with local `useState`. Promote to a shared store only when state genuinely needs to cross component boundaries.

## Data Fetching: Cache Library + Zod

- Use TanStack Query (or SWR) instead of `fetch` in `useEffect`. Validate API responses with Zod at the boundary and infer types from the schema. Always handle loading, error, and empty states.

```tsx
const User = z.object({ id: z.string(), email: z.string().email() })
type User = z.infer<typeof User>

export function useUser(id: string) {
  return useQuery({
    queryKey: ['user', id],
    queryFn: async (): Promise<User> => User.parse(await api.getUser(id)),
  })
}
```

## Lists: Virtualize

- Never render a large array in a `<ScrollView>` — there is no virtualization, memory grows linearly with the list, and scrolling becomes janky.
- Use `<FlatList>` with `keyExtractor`, `initialNumToRender`, and `windowSize`. For large or heterogeneous lists, use `FlashList` from Shopify.
- Memoize `renderItem` with `useCallback` and the row component with `memo` to avoid unnecessary re-renders on list data changes.

```tsx
<FlatList
  data={items}
  keyExtractor={(item) => item.id}
  renderItem={renderItem}
  initialNumToRender={10}
  windowSize={5}
/>
```

## Styling: Pick One System

- Use `StyleSheet.create()` (framework-native) or a utility-class library like NativeWind — not both. Choose one and stay consistent across the project.
- Never build style objects inline in JSX on hot paths. Inline objects are recreated every render and bypass the StyleSheet optimization pass.

```tsx
// NativeWind
<View className="p-4 rounded-2xl bg-white" />

// StyleSheet
const styles = StyleSheet.create({ card: { padding: 16, borderRadius: 16 } })
<View style={styles.card} />
```

## Native APIs: Wrap in Hooks, Always Clean Up

- Keep Expo SDK calls and subscriptions inside `use*` hooks, not in JSX. Always return a cleanup function from `useEffect`.
- Track whether the component is still mounted before applying async results. Use an `active` flag inside the effect.

```tsx
export function useCurrentLocation() {
  const [state, setState] = useState<LocationState>({ status: 'loading' })
  useEffect(() => {
    let active = true
    ;(async () => {
      const { status } = await Location.requestForegroundPermissionsAsync()
      if (!active) return
      if (status !== 'granted') { setState({ status: 'denied' }); return }
      const pos = await Location.getCurrentPositionAsync({})
      if (active) setState({ status: 'granted', coords: pos.coords })
    })()
    return () => { active = false }
  }, [])
  return state
}
```

## Secure Storage for Tokens

- Store auth tokens in `expo-secure-store`, which uses the device Keychain (iOS) or Keystore (Android). Never store secrets in `AsyncStorage` — it is unencrypted plaintext.

```tsx
await SecureStore.setItemAsync('auth_token', token)
const token = await SecureStore.getItemAsync('auth_token')
```

## Anti-Patterns

- Large array mapped inside a `<ScrollView>` (no virtualization). Use `FlatList` or `FlashList`.
- Server data copied into a Zustand store via `useEffect`. Let TanStack Query own server state.
- Tokens stored in `AsyncStorage`. Use `expo-secure-store`.
- Trusting deep-link params without Zod validation.
- Inline style objects on hot paths recreated every render.
- Secrets bundled in the app. Keep privileged API calls server-side; ship only public keys.
- Skipping loading, error, and empty state rendering. Always render all three.

## Platform-Specific Code

- Use `Platform.OS` checks for small differences. Extract to separate files (`Component.ios.tsx`, `Component.android.tsx`) only when the implementations diverge substantially.
- Confirm New Architecture compatibility for every native dependency before release.
- Respect safe areas (`useSafeAreaInsets`), Dynamic Type, and accessibility roles from the start — retrofitting is costly.
