#ifndef SCM_HYPOTHESIS_CHECKPOINT_H
#define SCM_HYPOTHESIS_CHECKPOINT_H

/* Complete two-component checkpoint with explicit little-endian integers and
 * IEEE-754 binary64 values. The core codec streams through caller callbacks;
 * it allocates no heap, full-record buffer or second rollback bank. Restore
 * decodes into workspace->staged and commits only after complete validation.
 * Caller objects, callback context and buffers must be nonoverlapping where
 * written. A callback returns the number of bytes transferred; any short
 * transfer is an IO error. record_bytes is the caller-verified record extent.
 * No observation is replayed or assimilated by either direction of the codec.
 *
 * CRC32 detects accidental corruption, not malicious edits. A target NVM
 * driver must manage inactive slots, commit markers, delivery deadlines and
 * power interruption; this byte codec alone does not qualify those behaviors.
 */
#include "scm_hypothesis.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SCM_HYPOTHESIS_CHECKPOINT_VERSION 1u
#define SCM_HYPOTHESIS_CHECKPOINT_BYTES 3004u
#define SCM_HYPOTHESIS_CHECKPOINT_BUFFER_BYTES 128u
#define SCM_HYPOTHESIS_CHECKPOINT_PATH_CAPACITY 512u
enum {
    SCM_HYPOTHESIS_CHECKPOINT_OK=0,
    SCM_HYPOTHESIS_CHECKPOINT_ERR_ARGUMENT=-120,
    SCM_HYPOTHESIS_CHECKPOINT_ERR_IO=-121,
    SCM_HYPOTHESIS_CHECKPOINT_ERR_FORMAT=-122,
    SCM_HYPOTHESIS_CHECKPOINT_ERR_INTEGRITY=-123,
    SCM_HYPOTHESIS_CHECKPOINT_ERR_INCOMPATIBLE=-124,
    SCM_HYPOTHESIS_CHECKPOINT_ERR_STATE=-125
};
typedef size_t (*scm_hypothesis_checkpoint_write_fn)(void*,const void*,size_t);
typedef size_t (*scm_hypothesis_checkpoint_read_fn)(void*,void*,size_t);

int scm_hypothesis_checkpoint_encode(const scm_hypothesis*,
    scm_hypothesis_checkpoint_write_fn,void*);
int scm_hypothesis_checkpoint_decode(scm_hypothesis*,const scm_hypothesis_config*,
    scm_hypothesis_checkpoint_read_fn,void*,size_t record_bytes,scm_hypothesis_workspace*);

#ifndef SCM_HYPOTHESIS_NO_HOST_IO
/* Optional POSIX adapter. Save uses a unique same-directory temporary file,
 * flush+fsync and rename. Restore closes the input before committing, so even
 * close failure leaves destination bytes unchanged. A caller-supplied128-byte
 * stdio buffer is charged explicitly. FILE/libc internals, a524-byte save path
 * frame and directory durability are separate host costs. Define
 * SCM_HYPOTHESIS_NO_HOST_IO for the callback-only embedded object. */
int scm_hypothesis_checkpoint_save(const scm_hypothesis*,const char*,
    unsigned char buffer[SCM_HYPOTHESIS_CHECKPOINT_BUFFER_BYTES]);
int scm_hypothesis_checkpoint_restore(scm_hypothesis*,const scm_hypothesis_config*,
    const char*,scm_hypothesis_workspace*,
    unsigned char buffer[SCM_HYPOTHESIS_CHECKPOINT_BUFFER_BYTES]);
#endif

#ifdef __cplusplus
}
#endif
#endif
