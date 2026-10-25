#ifndef SCM_ONLINE_CHECKPOINT_H
#define SCM_ONLINE_CHECKPOINT_H

/* Complete fixed-size host checkpoint for scm_online, explicit little-endian
 * integers and IEEE-754 binary64 values. Version/model/config/source and CRC32
 * detect incompatible or accidentally corrupted records, not malicious edits.
 *
 * Version 2 is 2456 bytes, independent of runtime/history length. It requires
 * model 2's lower-triangular factor and rejects version 1 without conversion.
 * No raw journal,
 * pointers, C padding or timing fields are serialized. Restore decodes into
 * workspace->candidate and validates before replacing the live state. The
 * workspace may change on failure; the destination does not.
 *
 * Save writes a unique same-directory temporary file, flushes+fsyncs it, then
 * atomically renames it. Directory-entry durability under power loss and an
 * embedded flash protocol remain unqualified. Path length must be below 512.
 * The codec reuses the workspace observation_gradient as a 128-byte stdio
 * buffer, plus small scalar codec buffers and a 524-byte save path on stack.
 * FILE/libc internals and nested frames are additional host-runtime costs.
 * State/config/path/workspace must be valid and nonoverlapping where written.
 */
#include "scm_online.h"
#ifdef __cplusplus
extern "C" {
#endif

#define SCM_ONLINE_CHECKPOINT_VERSION 2u
#define SCM_ONLINE_CHECKPOINT_BYTES 2456u
#define SCM_ONLINE_CHECKPOINT_PATH_CAPACITY 512u
enum {
    SCM_ONLINE_CHECKPOINT_OK=0,
    SCM_ONLINE_CHECKPOINT_ERR_ARGUMENT=-120,
    SCM_ONLINE_CHECKPOINT_ERR_IO=-121,
    SCM_ONLINE_CHECKPOINT_ERR_FORMAT=-122,
    SCM_ONLINE_CHECKPOINT_ERR_INTEGRITY=-123,
    SCM_ONLINE_CHECKPOINT_ERR_INCOMPATIBLE=-124,
    SCM_ONLINE_CHECKPOINT_ERR_STATE=-125
};

int scm_online_checkpoint_save(const scm_online*,const char*,scm_online_workspace*);
int scm_online_checkpoint_restore(scm_online*,const scm_online_config*,const char*,scm_online_workspace*);

#ifdef __cplusplus
}
#endif
#endif
