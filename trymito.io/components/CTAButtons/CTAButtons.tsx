import Link from 'next/link';
import { MITO_INSTALLATION_DOCS_LINK } from '../Header/Header';
import TextButton from '../TextButton/TextButton';
import styles from './CTAButtons.module.css'

const CTAButtons = (props: {variant: 'download' | 'contact'}): JSX.Element => {

    return (
        <div className={styles.cta_buttons_container}> 
            {props.variant === 'download' && 
                <TextButton 
                    text='Install Mito for Jupyter'
                    href={MITO_INSTALLATION_DOCS_LINK}
                />
            }
            {props.variant === 'contact' && 
                <TextButton 
                    text='Contact the Mito Team'
                    href="mailto:founders@sagacollab.com"
                />
            }
            <p className={styles.cta_subbutton}>
                <Link href='/plans'>
                    <a>
                        or see Pro plans →
                    </a>
                </Link>
            </p>
        </div>
    )
}

export default CTAButtons;