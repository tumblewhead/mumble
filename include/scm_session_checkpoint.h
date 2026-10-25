#ifndef SCM_SESSION_CHECKPOINT_H
#define SCM_SESSION_CHECKPOINT_H

/* Complete host checkpoint for scm_session. The format contains explicit
 * little-endian integers and IEEE-754 binary64 values, never C padding or
 * pointers. A version/model/numeric tag and CRC32 detect incompatible or
 * accidentally corrupted files; the CRC is not an authenticity mechanism.
 * Runtime CPU/basis timings are non-causal diagnostics and are encoded as
 * zero. Restoration does not invoke an optimizer or add another prior.
 *
 * Save uses a unique temporary file in the destination directory and replaces
 * the name only after the complete file has been flushed and synchronized.
 * Filesystem/power-loss durability of the directory entry is not qualified.
 * Restore is transactional: on failure the initialized or zeroed destination
 * and its owned journal remain unchanged. Objects must not alias arguments.
 * This host file API is not a Cortex-M23 persistence implementation.
 *
 * Version 1 file size is 2808 + 25*N bytes for N retained observations.
 * Restoration requests C*(sizeof(scm_sample)+1) journal bytes for saved
 * capacity C, alongside one candidate scm_session on the stack. A nonempty
 * destination keeps its old journal allocated until candidate validation is
 * complete. The decoder uses fixed buffers; stdio/allocator internals and
 * nested call frames are additional. Runtime peaks stored in the checkpoint
 * describe the stream/fit path, not this transient restore transaction.
 */
#include "scm_session.h"
#ifdef __cplusplus
extern "C" {
#endif

#define SCM_SESSION_CHECKPOINT_VERSION 1u
enum {
    SCM_SESSION_CHECKPOINT_OK=0,
    SCM_SESSION_CHECKPOINT_ERR_ARGUMENT=-80,
    SCM_SESSION_CHECKPOINT_ERR_IO=-81,
    SCM_SESSION_CHECKPOINT_ERR_FORMAT=-82,
    SCM_SESSION_CHECKPOINT_ERR_INTEGRITY=-83,
    SCM_SESSION_CHECKPOINT_ERR_INCOMPATIBLE=-84,
    SCM_SESSION_CHECKPOINT_ERR_LIMIT=-85,
    SCM_SESSION_CHECKPOINT_ERR_ALLOC=-86,
    SCM_SESSION_CHECKPOINT_ERR_STATE=-87
};

int scm_session_checkpoint_save(const scm_session *session,const char *path);
int scm_session_checkpoint_restore(scm_session *session,
    const scm_session_config *expected,const char *path);

#ifdef __cplusplus
}
#endif
#endif
